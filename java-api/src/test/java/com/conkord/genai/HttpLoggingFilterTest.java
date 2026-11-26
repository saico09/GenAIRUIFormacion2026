package com.conkord.genai;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.ServletOutputStream;
import jakarta.servlet.WriteListener;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class HttpLoggingFilterTest {
    private record Audit(Integer patientId, int status, String request, boolean requestTruncated) {}

    private final List<Audit> audits = new ArrayList<>();
    private final HttpLoggingFilter filter = new HttpLoggingFilter(JsonMapper.builder().build(), new TransactionLogRepository(null) {
        @Override public void record(Integer patientId, String operation, String method, String path, int status, String request,
                String response, double duration, boolean requestTruncated, boolean responseTruncated) {
            audits.add(new Audit(patientId, status, request, requestTruncated));
        }
    });
    private final AtomicLong bytesRead = new AtomicLong();
    private final Map<String, Object> responseState = new HashMap<>(Map.of("status", 200));
    private final ByteArrayOutputStream responseBody = new ByteArrayOutputStream();

    private HttpServletRequest request(String method, String uri, Map<String, String> headers, byte[] body, long declaredLength) {
        Map<String, Object> attributes = new HashMap<>();
        ServletInputStream stream = new ServletInputStream() {
            private final ByteArrayInputStream source = new ByteArrayInputStream(body);
            @Override public int read() { int value = source.read(); if (value >= 0) bytesRead.incrementAndGet(); return value; }
            @Override public int read(byte[] buffer, int offset, int length) {
                int read = source.read(buffer, offset, length);
                if (read > 0) bytesRead.addAndGet(read);
                return read;
            }
            @Override public boolean isFinished() { return source.available() == 0; }
            @Override public boolean isReady() { return true; }
            @Override public void setReadListener(ReadListener listener) { }
        };
        return (HttpServletRequest) Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[] {HttpServletRequest.class},
                (proxy, call, args) -> switch (call.getName()) {
                    case "getMethod" -> method;
                    case "getRequestURI" -> uri;
                    // Como Tomcat: decodificada y sin parámetros ';'.
                    case "getServletPath" -> java.net.URLDecoder.decode(uri.replaceAll(";[^/]*", ""), java.nio.charset.StandardCharsets.UTF_8);
                    case "getHeader" -> headers.get((String) args[0]);
                    case "getContentLengthLong" -> declaredLength;
                    case "getContentLength" -> (int) Math.min(declaredLength, Integer.MAX_VALUE);
                    case "getContentType" -> "application/json";
                    case "getCharacterEncoding" -> "UTF-8";
                    case "getInputStream" -> stream;
                    case "getAttribute" -> attributes.get((String) args[0]);
                    case "setAttribute" -> attributes.put((String) args[0], args[1]);
                    case "hashCode" -> 1;
                    case "equals" -> proxy == args[0];
                    default -> call.getReturnType() == boolean.class ? false : null;
                });
    }

    private HttpServletResponse response() {
        ServletOutputStream stream = new ServletOutputStream() {
            @Override public void write(int value) { responseBody.write(value); }
            @Override public boolean isReady() { return true; }
            @Override public void setWriteListener(WriteListener listener) { }
        };
        return (HttpServletResponse) Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[] {HttpServletResponse.class},
                (proxy, call, args) -> switch (call.getName()) {
                    case "setStatus" -> responseState.put("status", args[0]);
                    case "getStatus" -> responseState.get("status");
                    case "setHeader" -> responseState.put((String) args[0], args[1]);
                    case "getHeader" -> responseState.get((String) args[0]);
                    case "getOutputStream" -> stream;
                    case "getCharacterEncoding" -> "UTF-8";
                    case "hashCode" -> 1;
                    case "equals" -> proxy == args[0];
                    default -> call.getReturnType() == boolean.class ? false : null;
                });
    }

    @Test
    void bodyOverFourMegabytesIsRejectedWithoutReadingIt() throws Exception {
        var chainCalls = new AtomicInteger();
        FilterChain chain = (request, response) -> chainCalls.incrementAndGet();
        byte[] body = new byte[1024];
        filter.doFilterInternal(request("PUT", "/patients/1/history", Map.of(), body, HttpLoggingFilter.MAX_REQUEST_BYTES + 1),
                response(), chain);

        assertEquals(413, responseState.get("status"));
        assertEquals(0, chainCalls.get());
        assertEquals(0, bytesRead.get());
        assertTrue(responseBody.toString(StandardCharsets.UTF_8).contains("supera 4 MiB"));
        assertEquals(List.of(new Audit(1, 413, "", true)), audits);
    }

    @Test
    void corsPreflightIsNotAudited() throws Exception {
        var chainCalls = new AtomicInteger();
        FilterChain chain = (request, response) -> chainCalls.incrementAndGet();
        filter.doFilterInternal(request("OPTIONS", "/patients", Map.of("Origin", "http://localhost:8000",
                "Access-Control-Request-Method", "POST"), new byte[0], -1), response(), chain);

        assertEquals(1, chainCalls.get());
        assertTrue(audits.isEmpty());
        assertTrue(responseState.containsKey("X-Request-ID"));
    }

    @Test
    void unreadBodyIsDrainedOnlyUpToTheAuditLimit() throws Exception {
        byte[] body = new byte[2 * 1024 * 1024];
        java.util.Arrays.fill(body, (byte) 'x');
        FilterChain chain = (request, response) -> ((HttpServletResponse) response).setStatus(404);
        filter.doFilterInternal(request("POST", "/patients/no/existe", Map.of(), body, -1), response(), chain);

        assertEquals(1, audits.size());
        var audit = audits.getFirst();
        assertEquals(404, audit.status());
        assertEquals(null, audit.patientId());
        assertTrue(audit.requestTruncated());
        assertEquals(131072, audit.request().length());
        assertTrue(bytesRead.get() <= 131073 + 8192, "Se leyeron " + bytesRead.get() + " bytes");
        assertFalse(bytesRead.get() >= body.length);
    }

    @Test
    void auditOnlyAttributesDecimalPatientIds() throws Exception {
        FilterChain chain = (request, response) -> ((HttpServletResponse) response).setStatus(422);
        for (String uri : List.of("/patients/0x1", "/patients/01", "/patients/0", "/patients/99999999999",
                "/patients/%31", "/patients/7;v=1/history", "/patients/5%0A", "/patients//2")) {
            filter.doFilterInternal(request("GET", uri, Map.of(), new byte[0], 0), response(), chain);
        }
        filter.doFilterInternal(request("GET", "/patients/42/history", Map.of(), new byte[0], 0), response(), chain);
        assertEquals(java.util.Arrays.asList(null, 1, null, null, 1, null, null, null, 42), audits.stream().map(Audit::patientId).toList());
    }
}
