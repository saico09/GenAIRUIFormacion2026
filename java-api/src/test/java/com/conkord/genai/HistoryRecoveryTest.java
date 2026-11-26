package com.conkord.genai;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Stream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionSystemException;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.json.JsonMapper;

class HistoryRecoveryTest {
    private static final int ID = 7;
    private static final HistoryResponse.Entry ENTRY = new HistoryResponse.Entry("6ec12d52-872c-4d82-a6b8-235cbd99936c", "Reflujo", "", "Omeprazol");

    @TempDir Path directory;
    private Patient patient;
    private final List<MedicalConsultationRepository.Backup> backups = new ArrayList<>();
    private final List<HistoryResponse.Consultation> savedConsultations = new ArrayList<>();
    private int synchronizations;
    private boolean failOnSave;
    private PatientHistoryService service;
    private java.util.function.Function<PlatformTransactionManager, PatientHistoryService> withManager;

    private static final class NoDatabase extends AbstractPlatformTransactionManager {
        @Override protected Object doGetTransaction() { return new Object(); }
        @Override protected void doBegin(Object transaction, TransactionDefinition definition) { }
        @Override protected void doCommit(DefaultTransactionStatus status) { }
        @Override protected void doRollback(DefaultTransactionStatus status) { }
    }

    @BeforeEach
    void setUp() throws Exception {
        patient = new Patient("Ana QA", LocalDate.of(1990, 1, 2), "ana@example.com");
        var field = Patient.class.getDeclaredField("id");
        field.setAccessible(true);
        field.set(patient, ID);
        PatientRepository patients = (PatientRepository) Proxy.newProxyInstance(getClass().getClassLoader(),
                new Class<?>[] {PatientRepository.class}, (proxy, method, args) -> switch (method.getName()) {
                    case "findById" -> Optional.of(patient);
                    case "findAll" -> List.of(patient);
                    case "saveAndFlush" -> {
                        if (failOnSave) throw new IllegalStateException("Fallo simulado de SQL");
                        yield args[0];
                    }
                    case "hashCode" -> 1;
                    case "equals" -> proxy == args[0];
                    case "toString" -> "pacientes en memoria";
                    default -> null;
                });
        var consultations = new MedicalConsultationRepository(null, JsonMapper.builder().build()) {
            @Override public List<HistoryResponse.Consultation> list(Integer patientId) { return List.copyOf(savedConsultations); }
            @Override public Stored find(UUID id) {
                return savedConsultations.stream().filter(item -> item.id().equals(id.toString()))
                        .map(item -> new Stored(ID, "consultation", item.question(), item.directAnswer(),
                                item.ragAnswer(), item.model(), item.sources())).findFirst().orElse(null);
            }
            @Override public void consultation(Integer patientId, HistoryResponse.Consultation input, String filename,
                    String markdown, String revision) {
                savedConsultations.add(input);
                backups.add(new Backup("consultation", filename, markdown, revision));
            }
            @Override public Backup latest(Integer patientId) { return backups.isEmpty() ? null : backups.getLast(); }
            @Override public Backup latestRecoverable(Integer patientId) {
                return backups.reversed().stream().filter(item -> !item.kind().equals("deleted")).findFirst().orElse(null);
            }
            @Override public void snapshot(Integer patientId, String filename, String markdown, String revision, String kind) {
                backups.add(new Backup(kind, filename, markdown, revision));
            }
        };
        var diseases = new PatientDiseaseRepository(null) {
            @Override public void lock() { }
            @Override public void unlock() { }
            @Override public List<HistoryResponse.Entry> list(int patientId) { return List.of(); }
            @Override public void synchronize(int patientId, List<HistoryResponse.Entry> entries) { synchronizations++; }
        };
        withManager = manager -> new PatientHistoryService(patients, consultations, diseases, manager, directory.toString());
        service = withManager.apply(new NoDatabase());
    }

    private String valid() { return HistoryMarkdown.render(patient, List.of(ENTRY), List.of()); }

    private Path report() { return directory.resolve("paciente-7-ana-qa.md"); }

    private void backup(String kind, String markdown) {
        backups.add(new MedicalConsultationRepository.Backup(kind, report().getFileName().toString(), markdown, HistoryMarkdown.revision(markdown)));
    }

    private List<Path> rejected() throws Exception {
        try (Stream<Path> files = Files.list(directory)) {
            return files.filter(path -> path.getFileName().toString().startsWith("paciente-7-ana-qa.md.rechazado-")).toList();
        }
    }

    @Test
    void invalidFileIsSetAsideAndLatestValidBackupRestored() throws Exception {
        backup("snapshot", valid());
        byte[] damaged = (valid() + "ÿ").getBytes(StandardCharsets.UTF_8);
        damaged[damaged.length - 1] = (byte) 0xFF;
        Files.write(report(), damaged);

        var history = service.get(ID);

        assertEquals(valid(), history.markdown());
        assertEquals(valid(), Files.readString(report()));
        assertEquals(1, rejected().size());
        assertArrayEquals(damaged, Files.readAllBytes(rejected().getFirst()));
        assertTrue(rejected().getFirst().getFileName().toString().matches("paciente-7-ana-qa\\.md\\.rechazado-\\d{8}T\\d{6}Z(-\\d+)?"));
        assertEquals(0, synchronizations);
        assertEquals(1, backups.size());
    }

    @Test
    void foreignHeaderOrJournalAlsoRecover() throws Exception {
        backup("snapshot", valid());
        Files.writeString(report(), valid().replace("patient_id: 7", "patient_id: 8"));
        assertEquals(valid(), service.get(ID).markdown());
        Files.writeString(report(), valid() + "\n## Consultas registradas\n\nTexto que SQL no tiene.\n");
        assertEquals(valid(), service.get(ID).markdown());
        assertEquals(2, rejected().size());
    }

    @Test
    void withoutValidBackupTheFileIsKeptAndConflictReturned() throws Exception {
        backups.add(new MedicalConsultationRepository.Backup("snapshot", "paciente-7-ana-qa.md", valid(), "0".repeat(64)));
        backup("deleted", valid());
        String broken = valid().replace("### Tratamiento", "### Otra");
        Files.writeString(report(), broken);

        var error = assertThrows(ResponseStatusException.class, () -> service.get(ID));

        assertEquals(409, error.getStatusCode().value());
        assertEquals(broken, Files.readString(report()));
        assertTrue(rejected().isEmpty());
    }

    @Test
    void validFileOnlyRewritesSqlWhenItChanged() throws Exception {
        backup("snapshot", valid());
        Files.writeString(report(), valid());
        service.get(ID);
        assertEquals(0, synchronizations);
        assertEquals(1, backups.size());

        String edited = valid().replace("Omeprazol", "Omeprazol 20 mg");
        Files.writeString(report(), edited);
        assertEquals("Omeprazol 20 mg", service.get(ID).entries().getFirst().medication());
        assertEquals(1, synchronizations);
        assertEquals(edited, backups.getLast().markdown());
    }

    @Test
    void rollbackRestoresTheOriginalBytesAfterARecovery() throws Exception {
        backup("snapshot", valid());
        byte[] damaged = valid().replace("patient_id: 7", "patient_id: 9").getBytes(StandardCharsets.UTF_8);
        Files.write(report(), damaged);
        failOnSave = true;

        assertThrows(IllegalStateException.class, () -> service.update(ID, new PatientRequest("Ana QA", LocalDate.of(1990, 1, 2), "ana@example.com")));

        assertArrayEquals(damaged, Files.readAllBytes(report()));
        assertTrue(rejected().isEmpty());
    }

    @Test
    void deleteWithoutFileLeavesDeletedBackup() {
        backup("snapshot", valid());
        service.delete(ID);
        assertEquals("deleted", backups.getLast().kind());
        assertEquals(valid(), backups.getLast().markdown());
        assertFalse(Files.exists(report()));
    }

    @Test
    void deleteWorksWithUnreadableOrHugeFile() throws Exception {
        byte[] huge = new byte[HistoryMarkdown.MAX_BYTES + 10];
        java.util.Arrays.fill(huge, (byte) 'a');
        huge[0] = (byte) 0xFF;
        huge[1] = 0;
        Files.write(report(), huge);

        service.delete(ID);

        var deleted = backups.getLast();
        assertEquals("deleted", deleted.kind());
        assertTrue(deleted.markdown().startsWith("\uFFFD\uFFFDaaa"));
        assertEquals(HistoryMarkdown.revision(deleted.markdown()), deleted.revision());
        assertFalse(Files.exists(report()));
    }

    @Test
    void reportIsRestoredWhenCommitAndRollbackBothFail() throws Exception {
        var lost = new AbstractPlatformTransactionManager() {
            @Override protected Object doGetTransaction() { return new Object(); }
            @Override protected void doBegin(Object transaction, TransactionDefinition definition) { }
            @Override protected void doCommit(DefaultTransactionStatus status) {
                throw new TransactionSystemException("COMMIT sin respuesta");
            }
            @Override protected void doRollback(DefaultTransactionStatus status) {
                throw new TransactionSystemException("Conexión cerrada");
            }
        };
        backup("snapshot", valid());
        Files.writeString(report(), valid());
        byte[] before = Files.readAllBytes(report());
        assertThrows(TransactionSystemException.class,
                () -> withManager.apply(lost).addDisease(ID, new DiseaseRequest("Gastritis", "Dieta", "")));
        assertArrayEquals(before, Files.readAllBytes(report()));
    }

    @Test
    void questionMadeOnlyOfUnicodeSpacesIsRejectedLikePython() {
        var request = new ConsultationRequest(UUID.randomUUID().toString(), "\u00a0\u2007", "directa", "rag", "modelo", List.of());
        var error = assertThrows(ResponseStatusException.class, () -> service.consult(ID, request));
        assertEquals(422, error.getStatusCode().value());
        assertEquals("question: Escribe una pregunta", error.getReason());
    }

    @Test
    void completeContextIsKeptWhenSavingAndRetryingAConsultation() throws Exception {
        backup("snapshot", valid());
        Files.writeString(report(), valid());
        var sources = java.util.stream.IntStream.range(0, 9)
                .mapToObj(index -> Map.<String, Object>of("patient_id", ID, "chunk_id", "fragmento-" + index)).toList();
        var request = new ConsultationRequest(UUID.randomUUID().toString(), "Consulta sintética", "Sin RAG", "Con RAG", "modelo", sources);

        var first = service.consult(ID, request);
        var retried = service.consult(ID, request);

        assertTrue(first.created());
        assertFalse(retried.created());
        assertEquals(1, savedConsultations.size());
        assertEquals(sources, savedConsultations.getFirst().sources());
        assertEquals(sources, retried.history().consultations().getFirst().sources());
        assertEquals(first.history().markdown(), Files.readString(report()));
        assertEquals(first.history().markdown(), backups.getLast().markdown());
    }

    @Test
    void storedNameIsNotRequiredToBeValidWhenRenaming() throws Exception {
        var field = Patient.class.getDeclaredField("name");
        field.setAccessible(true);
        field.set(patient, "Ana\u0007QA");
        String legacy = HistoryMarkdown.render(patient, List.of(ENTRY), List.of());
        Files.writeString(directory.resolve("paciente-7-anaqa.md"), legacy);
        assertEquals(409, assertThrows(ResponseStatusException.class, () -> service.get(ID)).getStatusCode().value());

        service.update(ID, new PatientRequest("Ana QA", LocalDate.of(1990, 1, 2), "ana@example.com"));

        assertEquals(valid(), Files.readString(report()));
        assertFalse(Files.exists(directory.resolve("paciente-7-anaqa.md")));
    }
}
