package com.conkord.genai;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import tools.jackson.databind.json.JsonMapper;

/** SQL explícito y pequeño: las consultas y las revisiones conservan el Markdown exacto. */
@Repository
public class MedicalConsultationRepository {
    private final JdbcTemplate jdbc;
    private final JsonMapper mapper;

    public MedicalConsultationRepository(JdbcTemplate jdbc, JsonMapper mapper) { this.jdbc = jdbc; this.mapper = mapper; }

    public List<HistoryResponse.Consultation> list(Integer patientId) {
        return jdbc.query("""
                SELECT id, question, direct_answer, rag_answer, model, created_at, sources::text AS sources
                FROM public.medical_consultations WHERE patient_id = ? AND kind = 'consultation'
                ORDER BY storage_order
                """, (row, n) -> new HistoryResponse.Consultation(row.getString("id"), row.getString("question"),
                        row.getString("direct_answer"), row.getString("rag_answer"), row.getString("model"),
                        row.getTimestamp("created_at").toInstant().toString(), sources(row.getString("sources"))), patientId);
    }

    public Stored find(UUID id) {
        var rows = jdbc.query("""
                SELECT patient_id, kind, question, direct_answer, rag_answer, model, sources::text AS sources
                FROM public.medical_consultations WHERE id = ?
                """, (row, n) -> new Stored(row.getInt("patient_id"), row.getString("kind"),
                        row.getString("question"), row.getString("direct_answer"), row.getString("rag_answer"),
                        row.getString("model"), sources(row.getString("sources"))), id);
        return rows.isEmpty() ? null : rows.getFirst();
    }

    public void consultation(Integer patientId, HistoryResponse.Consultation input, String filename,
            String markdown, String revision) {
        UUID id = UUID.fromString(input.id());
        jdbc.update("""
                INSERT INTO public.medical_consultations
                (id, execution_id, patient_id, kind, question, direct_answer, rag_answer, model,
                 filename, markdown_content, revision, created_at, sources)
                VALUES (?, ?, ?, 'consultation', ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb))
                """, id, id, patientId, input.question(), input.directAnswer(), input.ragAnswer(), input.model(),
                filename, markdown, revision, Timestamp.from(Instant.parse(input.createdAt())), mapper.writeValueAsString(input.sources()));
    }

    public void snapshot(Integer patientId, String filename, String markdown, String revision, String kind) {
        var previous = latest(patientId);
        // Comparar únicamente la última revisión permite respaldar A → B → A.
        if (!kind.equals("deleted") && previous != null && previous.revision().equals(revision)
                && previous.filename().equals(filename)) return;
        jdbc.update("""
                INSERT INTO public.medical_consultations
                (id, execution_id, patient_id, kind, filename, markdown_content, revision)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, UUID.randomUUID(), executionId(), patientId, kind, filename, markdown, revision);
    }

    public Backup latest(Integer patientId) {
        var rows = jdbc.query("""
                SELECT filename, markdown_content, revision FROM public.medical_consultations
                WHERE patient_id = ? ORDER BY storage_order DESC LIMIT 1
                """, (row, n) -> new Backup(row.getString("filename"), row.getString("markdown_content"),
                        row.getString("revision")), patientId);
        return rows.isEmpty() ? null : rows.getFirst();
    }

    static UUID executionId() {
        if (RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attributes
                && attributes.getRequest().getAttribute("execution_id") instanceof UUID id) return id;
        return UUID.randomUUID();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> sources(String json) { return mapper.readValue(json, List.class); }

    public String serializeSources(List<Map<String, Object>> sources) { return mapper.writeValueAsString(sources); }

    public record Stored(int patientId, String kind, String question, String directAnswer, String ragAnswer, String model,
            List<Map<String, Object>> sources) {
        public boolean matches(int patientId, ConsultationRequest request) {
            return this.patientId == patientId && kind.equals("consultation") && question.equals(request.question())
                    && directAnswer.equals(request.directAnswer()) && ragAnswer.equals(request.ragAnswer())
                    && model.equals(request.model()) && sources.equals(request.sources());
        }
    }
    public record Backup(String filename, String markdown, String revision) {}
}
