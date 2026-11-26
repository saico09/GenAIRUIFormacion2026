package com.conkord.genai;

import java.io.IOException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.UUID;
import java.util.function.Supplier;

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
    private static final DateTimeFormatter REJECTED_SUFFIX = DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'").withZone(ZoneOffset.UTC);
    private final PatientRepository patients;
    private final MedicalConsultationRepository consultations;
    private final PatientDiseaseRepository diseases;
    private final TransactionTemplate transactions;
    private final Path directory;
    // Bytes previos de cada archivo tocado: también se restauran archivos ilegibles o de más de 1 MiB.
    private final ThreadLocal<LinkedHashMap<Path, byte[]>> beforeWrites = new ThreadLocal<>();

    public PatientHistoryService(PatientRepository patients, MedicalConsultationRepository consultations,
            PatientDiseaseRepository diseases, PlatformTransactionManager manager,
            @Value("${app.history.dir}") String directory) {
        this.patients = patients;
        this.consultations = consultations;
        this.diseases = diseases;
        if (manager instanceof AbstractPlatformTransactionManager springTransactions) {
            // Un COMMIT fallido termina como rollback y, si el rollback también falla (estado desconocido),
            // afterCompletion igual restaura los archivos: sólo un COMMIT confirmado los conserva.
            springTransactions.setRollbackOnCommitFailure(true);
        }
        this.transactions = new TransactionTemplate(manager);
        this.directory = Path.of(directory).toAbsolutePath().normalize();
    }

    private <T> T locked(Supplier<T> action) {
        return transactions.execute(status -> {
            diseases.lock();
            var before = new LinkedHashMap<Path, byte[]>();
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override public void afterCompletion(int completion) {
                    // Un cierre forzado impide esta compensación. load() recupera informes ausentes o inválidos;
                    // un Markdown válido editado se sincroniza a SQL, igual que una edición manual.
                    try {
                        if (completion != STATUS_COMMITTED) {
                            for (var item : before.entrySet()) {
                                try {
                                    if (item.getValue() == null) Files.deleteIfExists(item.getKey());
                                    else writeRaw(item.getKey(), item.getValue());
                                } catch (Exception recovery) {
                                    log.error("No se pudo restaurar {} tras rollback", item.getKey().getFileName(), recovery);
                                }
                            }
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
    public PatientResponse update(int id, PatientRequest input) { return locked(() -> updateLocked(id, input)); }
    public void delete(int id) { locked(() -> { deleteLocked(id); return null; }); }
    public HistoryResponse get(int id) { return locked(() -> load(findPatient(id), true)); }
    public HistoryResponse replace(int id, HistoryRequest.Replace input) { return locked(() -> replaceLocked(id, input)); }
    public HistoryResponse append(int id, HistoryRequest.Append input) { return locked(() -> appendLocked(id, input)); }
    public ConsultationSaved consult(int id, ConsultationRequest input) { return locked(() -> consultLocked(id, input)); }

    /** Las consultas guardadas no cambian: se leen de SQL sin esperar el bloqueo clínico. */
    public HistoryResponse.Consultation getConsultation(int id, String consultationId) {
        findPatient(id);
        var consultation = consultations.findConsultation(id, UUID.fromString(consultationId));
        if (consultation == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Consulta no encontrada");
        return consultation;
    }

    private PatientResponse createLocked(PatientRequest input) {
        Patient patient = patients.saveAndFlush(new Patient(input.name(), input.birthDate(), input.email()));
        if (findFile(patient.getId()) != null) throw conflict("Ya existe un informe para este ID");
        Path path = filename(patient);
        String markdown = HistoryMarkdown.render(patient, List.of(), List.of());
        write(path, markdown);
        snapshot(patient, path.getFileName().toString(), markdown, "snapshot");
        return PatientResponse.from(patient);
    }

    private PatientResponse updateLocked(int id, PatientRequest input) {
        Patient previous = findPatient(id);
        // Sólo se valida el nombre nuevo: así un nombre heredado inválido se puede corregir.
        HistoryResponse history = load(previous, false);
        Path oldPath = directory.resolve(history.filename());
        previous.updateDetails(input.name(), input.birthDate(), input.email());
        patients.saveAndFlush(previous);
        Path newPath = filename(previous);
        if (!oldPath.equals(newPath) && Files.exists(newPath, LinkOption.NOFOLLOW_LINKS)) {
            throw conflict("Ya existe otro archivo con el nombre nuevo");
        }
        String markdown = HistoryMarkdown.render(previous, history.entries(), history.consultations());
        write(oldPath, markdown);
        if (!oldPath.equals(newPath)) move(oldPath, newPath);
        snapshot(previous, newPath.getFileName().toString(), markdown, "snapshot");
        return PatientResponse.from(previous);
    }

    private void deleteLocked(int id) {
        Patient patient = findPatient(id);
        Path path = findFile(id);
        if (path != null) {
            // Se borra aunque el informe sea ilegible o supere 1 MiB: el respaldo guarda sus bytes con reemplazo.
            byte[] bytes = io(() -> Files.readAllBytes(path));
            snapshot(patient, path.getFileName().toString(), lenient(bytes), "deleted");
        } else {
            var backup = consultations.latest(id);
            if (backup != null) snapshot(patient, backup.filename(), backup.markdown(), "deleted");
            else snapshot(patient, filename(patient).getFileName().toString(),
                    HistoryMarkdown.render(patient, diseases.list(id), consultations.list(id)), "deleted");
        }
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
            } catch (ResponseStatusException error) {
                // No se sobrescribe un archivo conflictivo ni se impide usar otros pacientes.
                log.error("No se pudo respaldar el informe del paciente {}: HTTP {} {}", patient.getId(),
                        error.getStatusCode().value(), error.getReason(), error.getCause());
            } catch (RuntimeException error) {
                log.error("No se pudo respaldar el informe del paciente {}", patient.getId(), error);
            }
        }
    }

    private ConsultationSaved consultLocked(int id, ConsultationRequest input) {
        Patient patient = findPatient(id);
        UUID consultationId = UUID.fromString(input.id());
        var existing = consultations.find(consultationId);
        if (existing != null) {
            if (!existing.matches(id, input)) throw conflict("El UUID ya pertenece a otra consulta; no se sobrescribió");
            return new ConsultationSaved(load(patient, true), false);
        }
        // Como en Python: una pregunta hecha sólo de espacios Unicode (U+00A0…) está vacía.
        if (InputRules.trim(input.question()).isEmpty()) throw invalid("question: Escribe una pregunta");
        checkConsultationText(input.question());
        checkConsultationText(input.directAnswer());
        checkConsultationText(input.ragAnswer());
        if (input.model().codePoints().anyMatch(Character::isISOControl)) throw invalid("model: no admite caracteres de control");
        if (!InputRules.storable(input.sources())) throw invalid("sources: no admite U+0000 ni caracteres Unicode inválidos");
        if (input.sources().stream().anyMatch(source -> source == null
                || !(source.get("patient_id") instanceof Integer owner) || owner.intValue() != id)) {
            throw invalid("Cada fuente debe pertenecer al paciente de la consulta");
        }
        if (consultations.serializeSources(input.sources()).getBytes(StandardCharsets.UTF_8).length > 50000) {
            throw invalid("Las fuentes de la consulta exceden 50 KiB");
        }
        HistoryResponse current = load(patient, true);
        var journal = new ArrayList<>(current.consultations());
        var consultation = new HistoryResponse.Consultation(input.id(), input.question(), input.directAnswer(),
                input.ragAnswer(), input.model(), Instant.now().truncatedTo(ChronoUnit.MICROS).toString(), input.sources());
        journal.add(consultation);
        String markdown = HistoryMarkdown.render(patient, current.entries(), journal);
        HistoryMarkdown.checkSize(markdown);
        Path path = directory.resolve(current.filename());
        consultations.consultation(id, consultation, current.filename(), markdown, HistoryMarkdown.revision(markdown));
        write(path, markdown);
        return new ConsultationSaved(response(patient, current.filename(), markdown, current.entries(), journal), true);
    }

    public record ConsultationSaved(HistoryResponse history, boolean created) {}

    private HistoryResponse replaceLocked(int id, HistoryRequest.Replace input) {
        Patient patient = findPatient(id);
        HistoryResponse current = load(patient, true);
        checkRevision(input.revision(), current);
        List<HistoryResponse.Entry> entries = HistoryMarkdown.parse(patient, input.markdown(), current.consultations());
        var existing = new HashSet<>(current.entries().stream().map(HistoryResponse.Entry::id).toList());
        if (entries.stream().anyMatch(entry -> !existing.contains(entry.id()))) {
            throw invalid("Los UUID existentes no se cambian; crea nuevos registros desde Agregar registro");
        }
        return save(patient, current, entries);
    }

    private HistoryResponse appendLocked(int id, HistoryRequest.Append input) {
        Patient patient = findPatient(id);
        HistoryResponse current = load(patient, true);
        checkRevision(input.revision(), current);
        var entries = new ArrayList<>(current.entries());
        entries.add(HistoryMarkdown.entry(UUID.randomUUID().toString(), input.disease(), input.treatment(), input.medication()));
        if (entries.size() > HistoryMarkdown.MAX_ENTRIES) throw invalid("La historia admite como máximo 50 registros");
        return save(patient, current, entries);
    }

    public List<DiseaseResponse> listDiseases(int id) {
        return locked(() -> load(findPatient(id), true).entries().stream().map(item -> DiseaseResponse.from(id, item)).toList());
    }

    public DiseaseResponse getDisease(int id, String diseaseId) {
        return locked(() -> DiseaseResponse.from(id, findEntry(load(findPatient(id), true), diseaseId)));
    }

    public DiseaseResponse addDisease(int id, DiseaseRequest input) {
        // Se valida antes del bloqueo, como Python: un cuerpo inválido es 422 aunque el paciente no exista.
        var item = HistoryMarkdown.entry(UUID.randomUUID().toString(), input.disease(), input.treatment(), input.medication());
        return locked(() -> {
            Patient patient = findPatient(id);
            HistoryResponse current = load(patient, true);
            if (current.entries().size() >= HistoryMarkdown.MAX_ENTRIES) throw invalid("La historia admite como máximo 50 registros");
            var entries = new ArrayList<>(current.entries());
            entries.add(item);
            save(patient, current, entries);
            return DiseaseResponse.from(id, item);
        });
    }

    public DiseaseResponse updateDisease(int id, String diseaseId, DiseaseRequest input) {
        var item = HistoryMarkdown.entry(diseaseId, input.disease(), input.treatment(), input.medication());
        return locked(() -> {
            Patient patient = findPatient(id);
            HistoryResponse current = load(patient, true);
            var previous = findEntry(current, diseaseId);
            var entries = new ArrayList<>(current.entries());
            entries.set(entries.indexOf(previous), item);
            save(patient, current, entries);
            return DiseaseResponse.from(id, item);
        });
    }

    public void deleteDisease(int id, String diseaseId) {
        locked(() -> {
            Patient patient = findPatient(id);
            HistoryResponse current = load(patient, true);
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
        String markdown = HistoryMarkdown.render(patient, entries, previous.consultations());
        HistoryMarkdown.checkSize(markdown);
        Path path = directory.resolve(previous.filename());
        diseases.synchronize(patient.getId(), entries);
        write(path, markdown);
        snapshot(patient, previous.filename(), markdown, "snapshot");
        return response(patient, previous.filename(), markdown, entries, previous.consultations());
    }

    private HistoryResponse load(Patient patient, boolean checkStoredName) {
        // Un nombre guardado con saltos o controles rompería el título del informe.
        if (checkStoredName && patient.getName().codePoints().anyMatch(Character::isISOControl)) {
            throw conflict("El nombre guardado del paciente tiene caracteres de control; corrígelo con PUT /patients/" + patient.getId());
        }
        var journal = consultations.list(patient.getId());
        Path path = findFile(patient.getId());
        String markdown;
        List<HistoryResponse.Entry> entries;
        if (path == null) {
            path = filename(patient);
            var backup = consultations.latest(patient.getId());
            if (backup != null && !usable(patient, backup, journal)) {
                throw conflict("El respaldo del informe no supera la comprobación de integridad");
            }
            markdown = backup != null ? backup.markdown() : HistoryMarkdown.render(patient, diseases.list(patient.getId()), journal);
            try {
                entries = HistoryMarkdown.parse(patient, markdown, journal);
            } catch (ResponseStatusException invalidSql) {
                throw conflict("El informe regenerado desde SQL no es válido (" + invalidSql.getReason() + ")");
            }
            write(path, markdown);
        } else {
            try {
                markdown = HistoryMarkdown.decode(readBytes(path));
                entries = HistoryMarkdown.parse(patient, markdown, journal);
            } catch (ResponseStatusException invalidFile) {
                // Sólo un archivo inválido (422) se intenta recuperar; un fallo de disco sigue siendo 503.
                if (!HistoryMarkdown.isInvalid(invalidFile)) throw invalidFile;
                markdown = recover(patient, path, journal, invalidFile.getReason());
                entries = HistoryMarkdown.parse(patient, markdown, journal);
            }
        }
        String filename = path.getFileName().toString();
        String revision = HistoryMarkdown.revision(markdown);
        // Si ya es el último respaldo, SQL ya refleja este archivo: no se reescriben filas en cada lectura.
        var latest = consultations.latest(patient.getId());
        if (latest == null || latest.kind().equals("deleted") || !latest.revision().equals(revision)
                || !latest.filename().equals(filename)) {
            diseases.synchronize(patient.getId(), entries);
            snapshot(patient, filename, markdown, "snapshot");
        }
        return response(patient, filename, markdown, entries, journal);
    }

    /** Un corte antes del COMMIT deja un informe que SQL no reconoce: se aparta y se restaura el último respaldo válido. */
    private String recover(Patient patient, Path path, List<HistoryResponse.Consultation> journal, String reason) {
        var backup = consultations.latestRecoverable(patient.getId());
        if (backup == null || !usable(patient, backup, journal)) {
            throw conflict("El informe Markdown no es válido (" + reason + ") y no hay un respaldo válido; corrígelo o restáuralo");
        }
        String name = path.getFileName() + ".rechazado-" + REJECTED_SUFFIX.format(Instant.now());
        Path rejected = path.resolveSibling(name);
        // Dos recuperaciones en el mismo segundo no se pisan.
        for (int copy = 2; Files.exists(rejected, LinkOption.NOFOLLOW_LINKS); copy++) rejected = path.resolveSibling(name + "-" + copy);
        move(path, rejected);
        write(path, backup.markdown());
        log.warn("history_recovered patient_id={} rejected={} reason={}", patient.getId(), rejected.getFileName(), reason);
        return backup.markdown();
    }

    private boolean usable(Patient patient, MedicalConsultationRepository.Backup backup, List<HistoryResponse.Consultation> journal) {
        if (!backup.revision().equals(HistoryMarkdown.revision(backup.markdown()))) return false;
        try {
            HistoryMarkdown.parse(patient, backup.markdown(), journal);
            return true;
        } catch (ResponseStatusException invalidBackup) {
            return false;
        }
    }

    private void snapshot(Patient patient, String filename, String markdown, String kind) {
        consultations.snapshot(patient.getId(), filename, markdown, HistoryMarkdown.revision(markdown), kind);
    }

    private HistoryResponse response(Patient patient, String filename, String markdown, List<HistoryResponse.Entry> entries,
            List<HistoryResponse.Consultation> journal) {
        return new HistoryResponse(patient.getId(), filename, HistoryMarkdown.revision(markdown), markdown,
                List.copyOf(entries), List.copyOf(journal));
    }

    private void checkConsultationText(String text) {
        if (text.codePoints().anyMatch(c -> Character.isISOControl(c) && c != '\n' && c != '\r' && c != '\t')) {
            throw invalid("La consulta no admite caracteres de control");
        }
    }

    private Path filename(Patient patient) { return directory.resolve(HistoryMarkdown.filename(patient)); }

    private Path findFile(int id) {
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

    /** Lee como máximo 1 MiB: un archivo mayor es un informe inválido, no se carga entero en memoria. */
    private byte[] readBytes(Path path) {
        return io(() -> {
            if (Files.size(path) > HistoryMarkdown.MAX_BYTES) throw invalid("El Markdown admite como máximo 1 MiB UTF-8");
            return Files.readAllBytes(path);
        });
    }

    /** Respaldo de un borrado: los bytes inválidos se reemplazan por U+FFFD y PostgreSQL no admite U+0000. */
    private static String lenient(byte[] bytes) {
        try {
            return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPLACE)
                    .onUnmappableCharacter(CodingErrorAction.REPLACE).decode(ByteBuffer.wrap(bytes)).toString()
                    .replace('\u0000', '\uFFFD');
        } catch (IOException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private void write(Path path, String content) {
        HistoryMarkdown.checkSize(content);
        remember(path);
        writeRaw(path, content.getBytes(StandardCharsets.UTF_8));
    }

    private void remember(Path path) {
        var before = beforeWrites.get();
        if (before == null) throw new IllegalStateException("La escritura clínica requiere una transacción");
        if (!before.containsKey(path)) {
            before.put(path, io(() -> Files.exists(path, LinkOption.NOFOLLOW_LINKS) ? Files.readAllBytes(path) : null));
        }
    }

    private void writeRaw(Path path, byte[] content) {
        io(() -> {
            Files.createDirectories(directory);
            Path temporary = Files.createTempFile(directory, ".history-", ".tmp");
            try {
                Files.write(temporary, content);
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

    private void checkRevision(String revision, HistoryResponse current) {
        if (!current.revision().equals(revision)) throw conflict("La historia cambió; recarga antes de guardar");
    }

    private Patient findPatient(int id) {
        return patients.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Paciente no encontrado"));
    }

    private static ResponseStatusException invalid(String message) { return InputRules.invalid(message); }
    private static ResponseStatusException conflict(String message) { return new ResponseStatusException(HttpStatus.CONFLICT, message); }

    @FunctionalInterface
    private interface StorageAction<T> { T run() throws IOException; }

    private <T> T io(StorageAction<T> action) {
        try { return action.run(); }
        catch (IOException error) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "No se pudo leer o guardar el informe Markdown", error);
        }
    }
}
