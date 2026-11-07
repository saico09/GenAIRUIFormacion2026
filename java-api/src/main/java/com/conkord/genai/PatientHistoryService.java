package com.conkord.genai;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

/** Un bloqueo local serializa el CRUD y las revisiones de los informes de esta instancia. */
@Service
public class PatientHistoryService {
    private static final int MAX_BYTES = 65536;
    private static final int MAX_ENTRIES = 50;
    private static final String EMPTY = "No registrado.";
    private static final String UUID_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
    private static final Pattern ENTRY = Pattern.compile(
            "\\n## Registro (" + UUID_PATTERN + ")\\n\\n### Enfermedad\\n(.*?)"
            + "\\n\\n### Tratamiento\\n(.*?)\\n\\n### Medicamento\\n(.*?)(?=\\n## Registro |\\z)", Pattern.DOTALL);
    private static final Pattern HEADING = Pattern.compile("(?m)^#{1,6}(?:\\s|$)");
    private final PatientRepository patients;
    private final TransactionTemplate transactions;
    private final Path directory;

    public PatientHistoryService(PatientRepository patients, PlatformTransactionManager manager,
            @Value("${app.history.dir}") String directory) {
        this.patients = patients;
        this.transactions = new TransactionTemplate(manager);
        this.directory = Path.of(directory).toAbsolutePath().normalize();
    }

    public synchronized PatientResponse create(PatientRequest input) {
        checkName(input.name());
        Path[] created = new Path[1];
        try {
            return transactions.execute(status -> {
                Patient patient = patients.saveAndFlush(new Patient(input.name(), input.birthDate(), input.email()));
                if (findFile(patient.getId()) != null) throw conflict("Ya existe un informe para este ID");
                Path path = filename(patient);
                write(path, render(patient, List.of()));
                created[0] = path;
                return PatientResponse.from(patient);
            });
        } catch (RuntimeException error) {
            if (created[0] != null) compensate(error, () -> Files.deleteIfExists(created[0]));
            throw error;
        }
    }

    public synchronized PatientResponse update(Integer id, PatientRequest input) {
        checkName(input.name());
        Patient previous = findPatient(id);
        HistoryResponse history = load(previous);
        Path oldPath = directory.resolve(history.filename());
        Path[] newPath = {oldPath};
        try {
            return transactions.execute(status -> {
                Patient patient = findPatient(id);
                patient.updateDetails(input.name(), input.birthDate(), input.email());
                patients.saveAndFlush(patient);
                newPath[0] = filename(patient);
                write(oldPath, render(patient, history.entries()));
                if (!oldPath.equals(newPath[0])) move(oldPath, newPath[0]);
                return PatientResponse.from(patient);
            });
        } catch (RuntimeException error) {
            restore(error, oldPath, history.markdown(), newPath[0]);
            throw error;
        }
    }

    public synchronized void delete(Integer id) {
        Patient patient = findPatient(id);
        Path path = findFile(id);
        String before = path == null ? null : read(path);
        try {
            transactions.executeWithoutResult(status -> {
                patients.delete(patient);
                patients.flush();
                if (path != null) io(() -> { Files.delete(path); return null; });
            });
        } catch (RuntimeException error) {
            if (path != null) restore(error, path, before, path);
            throw error;
        }
    }

    public synchronized HistoryResponse get(Integer id) {
        return load(findPatient(id));
    }

    public synchronized HistoryResponse replace(Integer id, HistoryRequest.Replace input) {
        Patient patient = findPatient(id);
        HistoryResponse current = load(patient);
        checkRevision(input.revision(), current);
        List<HistoryResponse.Entry> entries = parse(patient, input.markdown());
        var existing = new HashSet<>(current.entries().stream().map(HistoryResponse.Entry::id).toList());
        if (entries.stream().anyMatch(entry -> !existing.contains(entry.id()))) {
            throw invalid("Los UUID existentes no se cambian; crea nuevos registros desde Agregar registro");
        }
        return save(patient, current.filename(), entries);
    }

    public synchronized HistoryResponse append(Integer id, HistoryRequest.Append input) {
        Patient patient = findPatient(id);
        HistoryResponse current = load(patient);
        checkRevision(input.revision(), current);
        var entries = new ArrayList<>(current.entries());
        entries.add(entry(UUID.randomUUID().toString(), input.disease(), input.treatment(), input.medication()));
        if (entries.size() > MAX_ENTRIES) throw invalid("La historia admite como máximo 50 registros");
        return save(patient, current.filename(), entries);
    }

    private HistoryResponse save(Patient patient, String filename, List<HistoryResponse.Entry> entries) {
        String markdown = render(patient, entries);
        checkSize(markdown);
        write(directory.resolve(filename), markdown);
        return response(patient, filename, markdown, entries);
    }

    private HistoryResponse load(Patient patient) {
        checkName(patient.getName());
        Path path = findFile(patient.getId());
        if (path == null) {
            path = filename(patient);
            write(path, render(patient, List.of()));
        }
        String markdown = read(path);
        return response(patient, path.getFileName().toString(), markdown, parse(patient, markdown));
    }

    private HistoryResponse response(Patient patient, String filename, String markdown, List<HistoryResponse.Entry> entries) {
        try {
            String revision = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(markdown.getBytes(StandardCharsets.UTF_8)));
            return new HistoryResponse(patient.getId(), filename, revision, markdown, List.copyOf(entries));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 no disponible", impossible);
        }
    }

    private List<HistoryResponse.Entry> parse(Patient patient, String markdown) {
        checkSize(markdown);
        String normalized = markdown.replace("\r\n", "\n");
        String header = header(patient);
        if (!normalized.startsWith(header)) throw invalid("El título y patient_id deben conservar el propietario del informe");
        String body = normalized.substring(header.length());
        var entries = new ArrayList<HistoryResponse.Entry>();
        var ids = new HashSet<String>();
        var matcher = ENTRY.matcher(body);
        int offset = 0;
        while (matcher.find()) {
            if (matcher.start() != offset) throw invalid("Estructura Markdown inválida");
            String id = matcher.group(1);
            if (!UUID.fromString(id).toString().equals(id) || !ids.add(id)) throw invalid("Cada registro requiere un UUID válido y único");
            entries.add(entry(id, matcher.group(2), matcher.group(3), matcher.group(4)));
            if (entries.size() > MAX_ENTRIES) throw invalid("La historia admite como máximo 50 registros");
            offset = matcher.end();
        }
        if (offset != body.length()) throw invalid("Usa Registro, Enfermedad, Tratamiento y Medicamento con sus encabezados originales");
        return entries;
    }

    private HistoryResponse.Entry entry(String id, String disease, String treatment, String medication) {
        String d = field(disease), t = field(treatment), m = field(medication);
        if (d.isEmpty() && t.isEmpty() && m.isEmpty()) throw invalid("Un registro necesita al menos un campo con información");
        return new HistoryResponse.Entry(id, d, t, m);
    }

    private String field(String value) {
        if (value == null) throw invalid("Los campos del registro deben ser texto");
        String text = value.replace("\r\n", "\n").strip();
        if (text.length() > 2000 || HEADING.matcher(text).find()
                || text.codePoints().anyMatch(c -> Character.isISOControl(c) && c != '\n' && c != '\t')) {
            throw invalid("Cada campo admite hasta 2000 caracteres, sin encabezados ni caracteres de control");
        }
        return text.equals(EMPTY) ? "" : text;
    }

    private String render(Patient patient, List<HistoryResponse.Entry> entries) {
        StringBuilder text = new StringBuilder(header(patient));
        for (var entry : entries) {
            text.append("\n## Registro ").append(entry.id()).append("\n\n### Enfermedad\n")
                    .append(shown(entry.disease())).append("\n\n### Tratamiento\n")
                    .append(shown(entry.treatment())).append("\n\n### Medicamento\n")
                    .append(shown(entry.medication())).append('\n');
        }
        return text.toString();
    }

    private String shown(String value) { return value.isEmpty() ? EMPTY : value; }

    private String header(Patient patient) {
        return "# Historia clínica ficticia — " + patient.getName()
                + "\n\nDatos ficticios para la formación.\n\npatient_id: " + patient.getId() + "\n";
    }

    private Path filename(Patient patient) {
        String slug = Normalizer.normalize(patient.getName(), Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "").toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", "-")
                .replaceAll("^-|-$", "");
        if (slug.length() > 80) slug = slug.substring(0, 80).replaceAll("-$", "");
        if (slug.isEmpty()) slug = "paciente";
        return directory.resolve("paciente-" + patient.getId() + "-" + slug + ".md");
    }

    private Path findFile(Integer id) {
        return io(() -> {
            Files.createDirectories(directory);
            try (var files = Files.list(directory)) {
                var matches = files.filter(path -> path.getFileName().toString()
                        .matches("paciente-" + id + "-[a-z0-9-]+\\.md")).toList();
                if (matches.size() > 1) throw conflict("Hay más de un informe para el mismo paciente; no se sobrescribió ninguno");
                if (matches.isEmpty()) return null;
                Path path = matches.getFirst();
                if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) throw conflict("El informe no es un archivo regular");
                return path;
            }
        });
    }

    private String read(Path path) {
        return io(() -> {
            if (Files.size(path) > MAX_BYTES) throw invalid("El Markdown admite como máximo 64 KiB UTF-8");
            return Files.readString(path, StandardCharsets.UTF_8);
        });
    }

    private void write(Path path, String content) {
        checkSize(content);
        io(() -> {
            Files.createDirectories(directory);
            Path temporary = Files.createTempFile(directory, ".history-", ".tmp");
            try {
                Files.writeString(temporary, content, StandardCharsets.UTF_8);
                Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } finally { Files.deleteIfExists(temporary); }
            return null;
        });
    }

    private void move(Path from, Path to) {
        io(() -> { Files.move(from, to, StandardCopyOption.ATOMIC_MOVE); return null; });
    }

    private void restore(RuntimeException original, Path oldPath, String content, Path newPath) {
        try {
            write(oldPath, content);
            if (!newPath.equals(oldPath)) io(() -> { Files.deleteIfExists(newPath); return null; });
        } catch (RuntimeException recovery) { original.addSuppressed(recovery); }
    }

    private void compensate(RuntimeException original, StorageAction<?> action) {
        try { io(action); } catch (RuntimeException recovery) { original.addSuppressed(recovery); }
    }

    private void checkSize(String text) {
        if (text == null || text.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES) throw invalid("El Markdown admite como máximo 64 KiB UTF-8");
    }

    private void checkName(String name) {
        if (name.codePoints().anyMatch(Character::isISOControl)) throw invalid("El nombre no puede contener saltos de línea ni caracteres de control");
    }

    private void checkRevision(String revision, HistoryResponse current) {
        if (!current.revision().equals(revision)) throw conflict("La historia cambió; recarga antes de guardar");
    }

    private Patient findPatient(Integer id) {
        return patients.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Paciente no encontrado"));
    }

    private ResponseStatusException invalid(String message) { return new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT, message); }
    private ResponseStatusException conflict(String message) { return new ResponseStatusException(HttpStatus.CONFLICT, message); }

    @FunctionalInterface
    private interface StorageAction<T> { T run() throws IOException; }

    private <T> T io(StorageAction<T> action) {
        try { return action.run(); }
        catch (IOException error) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "No se pudo leer o guardar el informe Markdown"); }
    }
}
