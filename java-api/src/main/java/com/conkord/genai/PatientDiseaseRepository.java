package com.conkord.genai;

import java.sql.SQLException;
import java.util.List;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

/** Proyección relacional del informe. Se escribe dentro del bloqueo clínico compartido. */
@Repository
public class PatientDiseaseRepository {
    private static final Logger log = LoggerFactory.getLogger(PatientDiseaseRepository.class);
    private static final long CLINICAL_LOCK = 71420261109L;
    static final String BUSY = "La historia está ocupada por otra operación; reintenta.";
    private final JdbcTemplate jdbc;

    public PatientDiseaseRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public void lock() {
        // No se espera sin límite ocupando una de las conexiones del pool.
        jdbc.execute("SET LOCAL lock_timeout = '5s'");
        try {
            jdbc.execute("SELECT pg_advisory_xact_lock(" + CLINICAL_LOCK + ")");
            // Mantiene exclusión también entre rollback SQL y compensación del archivo.
            jdbc.execute("SELECT pg_advisory_lock(" + CLINICAL_LOCK + ")");
        } catch (DataAccessException error) {
            if (error.getMostSpecificCause() instanceof SQLException sql && "55P03".equals(sql.getSQLState())) {
                throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, BUSY, error);
            }
            throw error;
        }
    }

    public void unlock() {
        try {
            if (Boolean.TRUE.equals(jdbc.queryForObject("SELECT pg_advisory_unlock(" + CLINICAL_LOCK + ")", Boolean.class))) return;
            log.error("pg_advisory_unlock devolvió false; se liberan todos los bloqueos de sesión de esta conexión");
        } catch (RuntimeException error) {
            log.error("No se pudo liberar el bloqueo clínico; se intenta pg_advisory_unlock_all", error);
        }
        try {
            jdbc.execute("SELECT pg_advisory_unlock_all()");
        } catch (RuntimeException error) {
            log.error("pg_advisory_unlock_all falló; se descarta la conexión para no devolver un bloqueo al pool", error);
            try {
                // Cerrar la conexión física hace que PostgreSQL libere sus bloqueos; Hikari la retira del pool.
                jdbc.execute((ConnectionCallback<Void>) connection -> { connection.abort(Runnable::run); return null; });
            } catch (RuntimeException abort) {
                log.error("No se pudo descartar la conexión del bloqueo clínico", abort);
            }
        }
    }

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
            // El WHERE evita versiones nuevas de filas que no cambiaron.
            jdbc.update("""
                    INSERT INTO public.patient_diseases (id, patient_id, disease, treatment, medication)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET disease = EXCLUDED.disease,
                        treatment = EXCLUDED.treatment, medication = EXCLUDED.medication
                    WHERE (patient_diseases.disease, patient_diseases.treatment, patient_diseases.medication)
                        IS DISTINCT FROM (EXCLUDED.disease, EXCLUDED.treatment, EXCLUDED.medication)
                    """, UUID.fromString(entry.id()), patientId, entry.disease(), entry.treatment(), entry.medication());
        }
    }
}
