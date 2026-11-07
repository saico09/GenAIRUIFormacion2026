package com.conkord.genai;

import java.io.IOException;
import java.time.Instant;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.web.util.ContentCachingRequestWrapper;
import org.springframework.web.util.ContentCachingResponseWrapper;
import tools.jackson.databind.ObjectWriter;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.databind.json.JsonMapper;

@Component
public class HttpLoggingFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger("http_json");
    private static final Pattern REQUEST_ID = Pattern.compile("[A-Za-z0-9._:-]{1,128}");
    private static final int BODY_LIMIT = 131072;
    private final ObjectWriter writer;
    private final TransactionLogRepository transactions;

    public HttpLoggingFilter(JsonMapper mapper, TransactionLogRepository transactions) {
        this.writer = mapper.writer().without(SerializationFeature.INDENT_OUTPUT);
        this.transactions = transactions;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        long start = System.nanoTime();
        String providedId = request.getHeader("X-Request-ID");
        String requestId = providedId != null && REQUEST_ID.matcher(providedId).matches()
                ? providedId : UUID.randomUUID().toString();
        UUID executionId = executionId(request.getHeader("X-Execution-ID"));
        request.setAttribute("execution_id", executionId);
        response.setHeader("X-Request-ID", requestId);
        response.setHeader("X-Execution-ID", executionId.toString());

        boolean audited = request.getRequestURI().equals("/patients") || request.getRequestURI().startsWith("/patients/");
        var cachedRequest = audited ? new ContentCachingRequestWrapper(request, BODY_LIMIT + 1) : null;
        var cachedResponse = audited ? new ContentCachingResponseWrapper(response) : null;

        boolean failed = true;
        try {
            filterChain.doFilter(audited ? cachedRequest : request, audited ? cachedResponse : response);
            failed = false;
        } finally {
            Object pattern = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            String route = pattern instanceof String value ? value : "unmatched";
            // Loki conserva metadatos. Los cuerpos pedidos por el usuario van sólo a PostgreSQL.
            log.info(writer.writeValueAsString(Map.of(
                    "timestamp", Instant.now().toString(),
                    "service", "springboot",
                    "event", "http",
                    "request_id", requestId,
                    "method", request.getMethod(),
                    "route", route,
                    "status", failed ? 500 : response.getStatus(),
                    "duration_ms", (System.nanoTime() - start) / 1_000_000.0)));
            if (audited) {
                try {
                    // Un 404/405 puede resolverse sin consumir el cuerpo. Se termina
                    // de leer para que también quede auditado, con caché acotada.
                    boolean unread = false;
                    try {
                        byte[] buffer = new byte[8192];
                        while (cachedRequest.getInputStream().read(buffer) != -1) { }
                    } catch (IOException closed) { unread = true; }
                    byte[] input = cachedRequest.getContentAsByteArray(), output = cachedResponse.getContentAsByteArray();
                    transactions.record(executionId, requestId, request.getMethod() + " " + route,
                            request.getMethod(), request.getRequestURI(), failed ? 500 : response.getStatus(),
                            body(input), body(output), (System.nanoTime() - start) / 1_000_000.0,
                            (unread && (request.getContentLengthLong() < 0 || input.length < request.getContentLengthLong()))
                                    || input.length > BODY_LIMIT || request.getContentLengthLong() > BODY_LIMIT,
                            output.length > BODY_LIMIT);
                } catch (RuntimeException auditFailure) {
                    // Una caída de auditoría no transforma un CRUD ya confirmado en un falso fallo.
                    log.error("No se pudo guardar transaction_logs; execution_id={}", executionId);
                    response.setHeader("X-Audit-Status", "unavailable");
                } finally {
                    cachedResponse.copyBodyToResponse();
                }
            }
        }
    }

    private UUID executionId(String supplied) {
        try {
            UUID id = UUID.fromString(supplied == null ? "" : supplied);
            if (id.toString().equalsIgnoreCase(supplied)) return id;
        } catch (IllegalArgumentException ignored) { }
        return UUID.randomUUID();
    }

    private String body(byte[] bytes) {
        return new String(Arrays.copyOf(bytes, Math.min(bytes.length, BODY_LIMIT)), StandardCharsets.UTF_8)
                .replace("\u0000", "\\u0000");
    }
}
