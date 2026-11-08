package com.conkord.genai;

import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class TransactionLogRepository {
    private final JdbcTemplate jdbc;
    public TransactionLogRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public void record(Integer patientId, String operation, String method, String path,
            int status, String request, String response, double duration, boolean requestTruncated, boolean responseTruncated) {
        jdbc.update("""
                INSERT INTO public.transaction_logs
                (id, patient_id, service, operation, method, path, http_status,
                 request_body, response_body, duration_ms, request_truncated, response_truncated)
                VALUES (?, ?, 'java', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, UUID.randomUUID(), patientId, operation, method, path, status,
                request, response, duration, requestTruncated, responseTruncated);
    }
}
