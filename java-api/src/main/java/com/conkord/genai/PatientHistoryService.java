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
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.UUID;
import java.util.function.Supplier;
import java.util.regex.Pattern;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.web.server.ResponseStatusException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** SQL y Markdown comparten un bloqueo PostgreSQL entre Java y Python. */
@Service
public class PatientHistoryService {
    private static final Logger log = LoggerFactory.getLogger(PatientHistoryService.class);
    private static final int MAX_BYTES = 1048576;
    private static final int MAX_ENTRIES = 50;
    private static final String EMPTY = "No registrado.";
    private static final String JOURNAL_HEADING = "\n## Consultas registradas\n";
    private static final String UUID_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
    private static final Pattern ENTRY = Pattern.compile(
            "\\n## Registro (" + UUID_PATTERN + ")\\n\\n### Enfermedad\\n(.*?)"
            + "\\n\\n### Tratamiento\\n(.*?)\\n\\n### Medicamento\\n(.*?)(?=\\n## Registro |\\z)", Pattern.DOTALL);
    private static final Pattern HEADING = Pattern.compile("(?m)^#{1,6}(?:\\s|$)");
    private final PatientRepository patients;
    private final MedicalConsultationRepository consultations;
    private final PatientDiseaseRepository diseases;
    private final TransactionTemplate transactions;
    private final Path directory;
    private final ThreadLocal<LinkedHashMap<Path, String>> beforeWrites = new ThreadLocal<>();

    public PatientHistoryService(PatientRepository patients, MedicalConsultationRepository consultations,
            PatientDiseaseRepository diseases, PlatformTransactionManager manager,
            @Value("${app.history.dir}") String directory) {
        this.patients = patients;
        this.consultations = consultations;
        this.diseases = diseases;
        if (manager instanceof AbstractPlatformTransactionManager springTransactions) {
            springTransactions.setRollbackOnCommitFailure(true);
        }
        this.transactions = new TransactionTemplate(manager);
        this.directory = Path.of(directory).toAbsolutePath().normalize();
    }

    private <T> T locked(Supplier<T> action) {
        return transactions.execute(status -> {
            diseases.lock();
            var before = new LinkedHashMap<Path, String>();
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override public void afterCompletion(int completion) {
                    try {
                        if (completion == STATUS_ROLLED_BACK) {
                            for (var item : before.entrySet()) {
                                try {
                                    if (item.getValue() == null) Files.deleteIfExists(item.getKey());
                                    else writeRaw(item.getKey(), item.getValue());
                                } catch (Exception recovery) {
                                    log.error("No se pudo restaurar {} tras rollback", item.getKey().getFileName(), recovery);
                                }
                            }
                        } else if (completion == STATUS_UNKNOWN && !before.isEmpty()) {
                            log.error("Resultado SQL desconocido; se conserva el Markdown para conciliación");
                        }
                    } finally {
                        // Spring aún conserva aquí la conexión transaccional; se libera antes de devolverla al pool.
                        diseases.unlock();
                    }
                }
            });
            beforeWrites.set(before);
            try { return action.get(); }
            finally { beforeWrites.remove(); }
        });
    }

    public PatientResponse create(PatientRequest input) { return locked(() -> createLocked(input)); }
    public PatientResponse update(Integer id, PatientRequest input) { return locked(() -> updateLocked(id, input)); }
    public void delete(Integer id) { locked(() -> { deleteLocked(id); return null; }); }
    public HistoryResponse get(Integer id) { return locked(() -> load(findPatient(id))); }
    public HistoryResponse replace(Integer id, HistoryRequest.Replace input) { return locked(() -> replaceLocked(id, input)); }
    public HistoryResponse append(Integer id, HistoryRequest.Append input) { return locked(() -> appendLocked(id, input)); }
    public ConsultationSaved consult(Integer id, ConsultationRequest input) { return locked(() -> consultLocked(id, input)); }
    public HistoryResponse.Consultation getConsultation(Integer id, String consultationId) {
        return locked(() -> getConsultationLocked(id, consultationId));
    }

    private PatientResponse createLocked(PatientRequest input) {
        checkName(input.name());
        Patient patient = patients.saveAndFlush(new Patient(input.name(), input.birthDate(), input.email()));
        if (findFile(patient.getId()) != null) throw conflict("Ya existe un informe para este ID");
        Path path = filename(patient);
        String markdown = render(patient, List.of(), List.of());
        write(path, markdown);
        snapshot(patient, path.getFileName().toString(), markdown, "snapshot");
        return PatientResponse.from(patient);
    }

    private PatientResponse updateLocked(Integer id, PatientRequest input) {
        checkName(input.name());
        Patient previous = findPatient(id);
        HistoryResponse history = load(previous);
        Path oldPath = directory.resolve(history.filename());
        previous.updateDetails(input.name(), input.birthDate(), input.email());
        patients.saveAndFlush(previous);
        Path newPath = filename(previous);
        String markdown = render(previous, history.entries(), history.consultations());
        write(oldPath, markdown);
        if (!oldPath.equals(newPath)) move(oldPath, newPath);
        snapshot(previous, newPath.getFileName().toString(), markdown, "snapshot");
        return PatientResponse.from(previous);
    }

    private void deleteLocked(Integer id) {
        Patient patient = findPatient(id);
        Path path = findFile(id);
        String before = path == null ? null : read(path);
        if (before != null) snapshot(patient, path.getFileName().toString(), before, "deleted");
        patients.delete(patient);
        patients.flush();
        if (path != null) {
            remember(path);
            io(() -> { Files.delete(path); return null; });
        }
    }

    public void backupExisting() {
        for (Patient patient : patients.findAll()) {
            try {
                get(patient.getId());
            } catch (RuntimeException error) {
                // No se sobrescribe un archivo conflictivo ni se impide usar otros pacientes.
                log.error("No se pudo respaldar el informe del paciente {}; tipo={}", patient.getId(), error.getClass().getSimpleName());
            }
        }
    }

    private HistoryResponse.Consultation getConsultationLocked(Integer id, String consultationId) {
        findPatient(id);
        return consultations.list(id).stream().filter(item -> item.id().equals(consultationId)).findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Consulta no encontrada"));
    }

    private ConsultationSaved consultLocked(Integer id, ConsultationRequest input) {
        Patient patient = findPatient(id);
        UUID consultationId = UUID.fromString(input.id());
        var existing = consultations.find(consultationId);
        if (existing != null) {
            if (!existing.matches(id, input)) throw conflict("El UUID ya pertenece a otra consulta; no se sobrescribió");
            return new ConsultationSaved(load(patient), false);
        }
        checkConsultationText(input.question());
        checkConsultationText(input.directAnswer());
        checkConsultationText(input.ragAnswer());
        if (input.model().codePoints().anyMatch(Character::isISOControl)) throw invalid("El nombre del modelo no admite caracteres de control");
        if (input.sources().stream().anyMatch(source -> source == null
                || !(source.get("patient_id") instanceof Integer owner) || owner.intValue() != id)) {
            throw invalid("Cada fuente debe pertenecer al paciente de la consulta");
        }
        if (consultations.serializeSources(input.sources()).getBytes(StandardCharsets.UTF_8).length > 50000) {
            throw invalid("Las fuentes de la consulta exceden 50 KiB");
        }
        HistoryResponse current = load(patient);
        var journal = new ArrayList<>(current.consultations());
        var consultation = new HistoryResponse.Consultation(input.id(), input.question(), input.directAnswer(),
                input.ragAnswer(), input.model(), Instant.now().truncatedTo(ChronoUnit.MICROS).toString(), input.sources());
        journal.add(consultation);
        String markdown = render(patient, current.entries(), journal);
        checkSize(markdown);
        Path path = directory.resolve(current.filename());
        consultations.consultation(id, consultation, current.filename(), markdown, revision(markdown));
        write(path, markdown);
        return new ConsultationSaved(response(patient, current.filename(), markdown, current.entries(), journal), true);
    }

    public record ConsultationSaved(HistoryResponse history, boolean created) {}

    private HistoryResponse replaceLocked(Integer id, HistoryRequest.Replace input) {
        Patient patient = findPatient(id);
        HistoryResponse current = load(patient);
        checkRevision(input.revision(), current);
        List<HistoryResponse.Entry> entries = parse(patient, input.markdown(), current.consultations());
        var existing = new HashSet<>(current.entries().stream().map(HistoryResponse.Entry::id).toList());
        if (entries.stream().anyMatch(entry -> !existing.contains(entry.id()))) {
            throw invalid("Los UUID existentes no se cambian; crea nuevos registros desde Agregar registro");
        }
        return save(patient, current, entries);
    }

    private HistoryResponse appendLocked(Integer id, HistoryRequest.Append input) {
        Patient patient = findPatient(id);
        HistoryResponse current = load(patient);
        checkRevision(input.revision(), current);
        var entries = new ArrayList<>(current.entries());
        entries.add(entry(UUID.randomUUID().toString(), input.disease(), input.treatment(), input.medication()));
        if (entries.size() > MAX_ENTRIES) throw invalid("La historia admite como máximo 50 registros");
        return save(patient, current, entries);
    }

    public List<DiseaseResponse> listDiseases(Integer id) {
        return locked(() -> load(findPatient(id)).entries().stream().map(item -> DiseaseResponse.from(id, item)).toList());
    }

    public DiseaseResponse getDisease(Integer id, String diseaseId) {
        return locked(() -> DiseaseResponse.from(id, findEntry(load(findPatient(id)), diseaseId)));
    }

    public DiseaseResponse addDisease(Integer id, DiseaseRequest input) {
        return locked(() -> {
            Patient patient = findPatient(id);
            HistoryResponse current = load(patient);
            if (current.entries().size() >= MAX_ENTRIES) throw invalid("La historia admite como máximo 50 registros");
            var item = entry(UUID.randomUUID().toString(), input.disease(), input.treatment(), input.medication());
            var entries = new ArrayList<>(current.entries());
            entries.add(item);
            save(patient, current, entries);
            return DiseaseResponse.from(id, item);
        });
    }

    public DiseaseResponse updateDisease(Integer id, String diseaseId, DiseaseRequest input) {
        return locked(() -> {
            Patient patient = findPatient(id);
            HistoryResponse current = load(patient);
            var previous = findEntry(current, diseaseId);
            var item = entry(previous.id(), input.disease(), input.treatment(), input.medication());
            var entries = new ArrayList<>(current.entries());
            entries.set(entries.indexOf(previous), item);
            save(patient, current, entries);
            return DiseaseResponse.from(id, item);
        });
    }

    public void deleteDisease(Integer id, String diseaseId) {
        locked(() -> {
            Patient patient = findPatient(id);
            HistoryResponse current = load(patient);
            var previous = findEntry(current, diseaseId);
            var entries = new ArrayList<>(current.entries());
            entries.remove(previous);
            save(patient, current, entries);
            return null;
        });
    }

    private HistoryResponse.Entry findEntry(HistoryResponse history, String id) {
        return history.entries().stream().filter(item -> item.id().equals(id)).findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Registro no encontrado para este paciente"));
    }

    private HistoryResponse save(Patient patient, HistoryResponse previous, List<HistoryResponse.Entry> entries) {
        String markdown = render(patient, entries, previous.consultations());
        checkSize(markdown);
        Path path = directory.resolve(previous.filename());
        diseases.synchronize(patient.getId(), entries);
        write(path, markdown);
        snapshot(patient, previous.filename(), markdown, "snapshot");
        return response(patient, previous.filename(), markdown, entries, previous.consultations());
    }

    private HistoryResponse load(Patient patient) {
        checkName(patient.getName());
        Path path = findFile(patient.getId());
        if (path == null) {
            path = filename(patient);
            var backup = consultations.latest(patient.getId());
            if (backup != null) {
                if (!backup.revision().equals(revision(backup.markdown()))) throw conflict("El respaldo del informe no supera la comprobación de integridad");
                parse(patient, backup.markdown(), consultations.list(patient.getId()));
                write(path, backup.markdown());
            } else {
                write(path, render(patient, diseases.list(patient.getId()), consultations.list(patient.getId())));
            }
        }
        String markdown = read(path);
        var journal = consultations.list(patient.getId());
        var entries = parse(patient, markdown, journal);
        diseases.synchronize(patient.getId(), entries);
        snapshot(patient, path.getFileName().toString(), markdown, "snapshot");
        return response(patient, path.getFileName().toString(), markdown, entries, journal);
    }

    private void snapshot(Patient patient, String filename, String markdown, String kind) {
        consultations.snapshot(patient.getId(), filename, markdown, revision(markdown), kind);
    }

    private HistoryResponse response(Patient patient, String filename, String markdown, List<HistoryResponse.Entry> entries,
            List<HistoryResponse.Consultation> journal) {
        return new HistoryResponse(patient.getId(), filename, revision(markdown), markdown, List.copyOf(entries), List.copyOf(journal));
    }

    private String revision(String markdown) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(markdown.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 no disponible", impossible);
        }
    }

    private List<HistoryResponse.Entry> parse(Patient patient, String markdown, List<HistoryResponse.Consultation> journal) {
        checkSize(markdown);
        String normalized = markdown.replace("\r\n", "\n");
        String header = header(patient);
        if (!normalized.startsWith(header)) throw invalid("El título y patient_id deben conservar el propietario del informe");
        String body = normalized.substring(header.length());
        String journalText = renderJournal(journal);
        int journalStart = body.indexOf(JOURNAL_HEADING);
        if (journalStart >= 0) {
            if (!body.substring(journalStart).equals(journalText)) throw invalid("Las consultas automáticas son históricas; edita sólo los registros confirmados antes de Consultas registradas");
            body = body.substring(0, journalStart);
        } else if (!journal.isEmpty()) {
            throw invalid("Conserva la sección Consultas registradas sin cambios");
        }
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

    private String render(Patient patient, List<HistoryResponse.Entry> entries, List<HistoryResponse.Consultation> journal) {
        StringBuilder text = new StringBuilder(header(patient));
        for (var entry : entries) {
            text.append("\n## Registro ").append(entry.id()).append("\n\n### Enfermedad\n")
                    .append(shown(entry.disease())).append("\n\n### Tratamiento\n")
                    .append(shown(entry.treatment())).append("\n\n### Medicamento\n")
                    .append(shown(entry.medication())).append('\n');
        }
        return text.append(renderJournal(journal)).toString();
    }

    private String renderJournal(List<HistoryResponse.Consultation> journal) {
        if (journal.isEmpty()) return "";
        StringBuilder text = new StringBuilder(JOURNAL_HEADING)
                .append("\nConversaciones guardadas automáticamente. La nota describe lo reportado; las respuestas de IA no son diagnósticos confirmados.\n");
        for (var item : journal) {
            text.append("\n### Consulta ").append(item.id()).append("\n\nFecha UTC: ").append(item.createdAt())
                    .append("\n\nModelo: ").append(item.model()).append("\n\n#### Nota reportada\n")
                    .append(quoted(item.question())).append("\n\n#### Respuesta sin RAG\n")
                    .append(quoted(item.directAnswer())).append("\n\n#### Respuesta con RAG\n")
                    .append(quoted(item.ragAnswer())).append('\n');
        }
        return text.toString();
    }

    private String quoted(String text) { return "> " + text.replace("\r\n", "\n").replace('\r', '\n').replace("\n", "\n> "); }

    private void checkConsultationText(String text) {
        if (text.codePoints().anyMatch(c -> Character.isISOControl(c) && c != '\n' && c != '\r' && c != '\t')) {
            throw invalid("La consulta no admite caracteres de control");
        }
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
            if (Files.size(path) > MAX_BYTES) throw invalid("El Markdown admite como máximo 1 MiB UTF-8");
            return Files.readString(path, StandardCharsets.UTF_8);
        });
    }

    private void write(Path path, String content) {
        checkSize(content);
        remember(path);
        writeRaw(path, content);
    }

    private void remember(Path path) {
        var before = beforeWrites.get();
        if (before == null) throw new IllegalStateException("La escritura clínica requiere una transacción");
        if (!before.containsKey(path)) before.put(path, Files.exists(path) ? read(path) : null);
    }

    private void writeRaw(Path path, String content) {
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
        remember(from);
        remember(to);
        io(() -> { Files.move(from, to, StandardCopyOption.ATOMIC_MOVE); return null; });
    }

    private void checkSize(String text) {
        if (text == null || text.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES) throw invalid("El Markdown admite como máximo 1 MiB UTF-8");
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
