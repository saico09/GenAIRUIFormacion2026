package com.conkord.genai;

import java.io.IOException;
import java.time.Instant;
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
import tools.jackson.databind.ObjectWriter;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.databind.json.JsonMapper;

@Component
public class HttpLoggingFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger("http_json");
    private static final Pattern REQUEST_ID = Pattern.compile("[A-Za-z0-9._:-]{1,128}");
    private final ObjectWriter writer;

    public HttpLoggingFilter(JsonMapper mapper) {
        this.writer = mapper.writer().without(SerializationFeature.INDENT_OUTPUT);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        long start = System.nanoTime();
        String providedId = request.getHeader("X-Request-ID");
        String requestId = providedId != null && REQUEST_ID.matcher(providedId).matches()
                ? providedId : UUID.randomUUID().toString();
        response.setHeader("X-Request-ID", requestId);

        boolean failed = true;
        try {
            filterChain.doFilter(request, response);
            failed = false;
        } finally {
            Object pattern = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            String route = pattern instanceof String value ? value : "unmatched";
            // Solo metadatos de la petición: nunca ids de pacientes, query ni cuerpos.
            log.info(writer.writeValueAsString(Map.of(
                    "timestamp", Instant.now().toString(),
                    "service", "springboot",
                    "event", "http",
                    "request_id", requestId,
                    "method", request.getMethod(),
                    "route", route,
                    "status", failed ? 500 : response.getStatus(),
                    "duration_ms", (System.nanoTime() - start) / 1_000_000.0)));
        }
    }
}
