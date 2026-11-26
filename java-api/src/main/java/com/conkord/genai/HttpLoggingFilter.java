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
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.cors.CorsUtils;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.web.util.ContentCachingRequestWrapper;
import org.springframework.web.util.ContentCachingResponseWrapper;
import org.springframework.web.util.UriUtils;
import tools.jackson.databind.ObjectWriter;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.databind.json.JsonMapper;

@Component
public class HttpLoggingFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger("http_json");
    private static final Pattern REQUEST_ID = Pattern.compile("[A-Za-z0-9._:-]{1,128}");
    // Misma regla que la ruta: «/patients/01» es el paciente 1.
    private static final Pattern PATIENT_PATH = Pattern.compile("^/patients/([0-9]{1,10})(?:/|\\z)");
    private static final int BODY_LIMIT = 131072;
    // El Markdown admite 1 MiB y viaja escapado en JSON: 4 MiB deja margen sin agotar la memoria.
    static final long MAX_REQUEST_BYTES = 4L * 1024 * 1024;
    private final ObjectWriter writer;
    private final JsonMapper mapper;
    private final TransactionLogRepository transactions;

    public HttpLoggingFilter(JsonMapper mapper, TransactionLogRepository transactions) {
        this.writer = mapper.writer().without(SerializationFeature.INDENT_OUTPUT);
        this.mapper = mapper;
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
        MDC.put("request_id", requestId);
        MDC.put("execution_id", executionId.toString());
        try {
            handle(request, response, filterChain, start, requestId);
        } finally {
            MDC.remove("request_id");
            MDC.remove("execution_id");
        }
    }

    private void handle(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain,
            long start, String requestId) throws ServletException, IOException {
        // Un preflight CORS no es una transacción: no se guarda en transaction_logs.
        String path = request.getServletPath();
        boolean audited = (path.equals("/patients") || path.startsWith("/patients/")) && !CorsUtils.isPreFlightRequest(request);
        boolean tooLarge = request.getContentLengthLong() > MAX_REQUEST_BYTES;
        // Un cuerpo rechazado por tamaño no se envuelve: nunca se lee ni se reserva memoria para él.
        var cachedRequest = audited && !tooLarge ? new ContentCachingRequestWrapper(request, BODY_LIMIT + 1) : null;
        var cachedResponse = audited ? new ContentCachingResponseWrapper(response) : null;

        boolean failed = true;
        try {
            if (tooLarge) {
                HttpServletResponse target = audited ? cachedResponse : response;
                target.setStatus(HttpStatus.CONTENT_TOO_LARGE.value());
                target.setContentType(MediaType.APPLICATION_JSON_VALUE);
                target.setCharacterEncoding(StandardCharsets.UTF_8.name());
                target.getWriter().write("{\"detail\":\"El cuerpo de la petición supera 4 MiB\"}");
            } else {
                filterChain.doFilter(cachedRequest != null ? cachedRequest : request, audited ? cachedResponse : response);
            }
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
                    // Un 404/405 no consume el cuerpo: se lee hasta el límite + 1 byte para auditar el prefijo y marcar el recorte.
                    boolean unread = false;
                    if (cachedRequest != null) {
                        try {
                            var stream = cachedRequest.getInputStream();
                            byte[] buffer = new byte[8192];
                            long drained = cachedRequest.getContentAsByteArray().length;
                            int read;
                            while (drained <= BODY_LIMIT && (read = stream.read(buffer)) != -1) drained += read;
                        } catch (IOException closed) { unread = true; }
                    }
                    byte[] input = cachedRequest != null ? cachedRequest.getContentAsByteArray() : new byte[0];
                    byte[] output = cachedResponse.getContentAsByteArray();
                    transactions.record(patientId(request, output), request.getMethod() + " " + route,
                            request.getMethod(), request.getRequestURI(), failed ? 500 : response.getStatus(),
                            body(input), body(output), (System.nanoTime() - start) / 1_000_000.0,
                            (unread && (request.getContentLengthLong() < 0 || input.length < request.getContentLengthLong()))
                                    || input.length > BODY_LIMIT || request.getContentLengthLong() > BODY_LIMIT,
                            output.length > BODY_LIMIT);
                } catch (RuntimeException auditFailure) {
                    // Una caída de auditoría no transforma un CRUD ya confirmado en un falso fallo.
                    logger.error("No se pudo guardar transaction_logs", auditFailure);
                    response.setHeader("X-Audit-Status", "unavailable");
                } finally {
                    cachedResponse.copyBodyToResponse();
                }
            }
        }
    }

    private Integer patientId(HttpServletRequest request, byte[] output) {
        // Como scope["path"] en Python: decodificada, sin fusionar barras dobles ni quitar parámetros ';'.
        String path = request.getServletPath();
        var match = PATIENT_PATH.matcher(UriUtils.decode(request.getRequestURI(), StandardCharsets.UTF_8));
        if (match.find()) {
            long id = Long.parseLong(match.group(1));
            return id >= 1 && id <= Integer.MAX_VALUE ? (int) id : null;
        }
        // Crear un paciente todavía no tiene ID en la URL: se toma del resultado real.
        if (request.getMethod().equals("POST") && path.equals("/patients")) {
            try {
                var json = mapper.readTree(output);
                var id = json.get("id");
                if (id != null && id.isIntegralNumber() && id.canConvertToInt() && id.intValue() > 0) return id.intValue();
            } catch (RuntimeException ignored) { }
        }
        return null;
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
