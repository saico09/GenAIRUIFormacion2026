package com.conkord.genai;

import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

/** Proyección relacional del informe. Se escribe dentro del bloqueo clínico compartido. */
@Repository
public class PatientDiseaseRepository {
    private final JdbcTemplate jdbc;

    public PatientDiseaseRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public void lock() {
        jdbc.execute("SELECT pg_advisory_xact_lock(71420261109)");
        // Mantiene exclusión también entre rollback SQL y compensación del archivo.
        jdbc.execute("SELECT pg_advisory_lock(71420261109)");
    }

    public void unlock() { jdbc.execute("SELECT pg_advisory_unlock(71420261109)"); }

    public List<HistoryResponse.Entry> list(int patientId) {
        return jdbc.query("""
                SELECT id::text, disease, treatment, medication FROM public.patient_diseases
                WHERE patient_id = ? ORDER BY id
                """, (row, n) -> new HistoryResponse.Entry(row.getString("id"), row.getString("disease"),
                        row.getString("treatment"), row.getString("medication")), patientId);
    }

    public void synchronize(int patientId, List<HistoryResponse.Entry> entries) {
        for (var entry : entries) {
            var owners = jdbc.queryForList("SELECT patient_id FROM public.patient_diseases WHERE id = ?",
                    Integer.class, UUID.fromString(entry.id()));
            if (!owners.isEmpty() && owners.getFirst() != patientId) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "El UUID del registro pertenece a otro paciente");
            }
        }
        // Hay como máximo 50 filas: conservar UUID y sólo cambiar contenido evita un segundo modelo clínico.
        var ids = entries.stream().map(HistoryResponse.Entry::id).toList();
        for (String id : jdbc.queryForList("SELECT id::text FROM public.patient_diseases WHERE patient_id = ?",
                String.class, patientId)) {
            if (!ids.contains(id)) jdbc.update("DELETE FROM public.patient_diseases WHERE id = ? AND patient_id = ?",
                    UUID.fromString(id), patientId);
        }
        for (var entry : entries) {
            jdbc.update("""
                    INSERT INTO public.patient_diseases (id, patient_id, disease, treatment, medication)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET disease = EXCLUDED.disease,
                        treatment = EXCLUDED.treatment, medication = EXCLUDED.medication
                    """, UUID.fromString(entry.id()), patientId, entry.disease(), entry.treatment(), entry.medication());
        }
    }
}
