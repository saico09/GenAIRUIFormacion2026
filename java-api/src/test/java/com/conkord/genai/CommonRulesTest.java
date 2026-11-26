package com.conkord.genai;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

/** Vectores comunes: la API Python debe dar exactamente los mismos resultados. */
class CommonRulesTest {
    private static final String EMOJI = "😀";
    private static final LocalDate BIRTH = LocalDate.of(1990, 1, 2);
    private static ValidatorFactory factory;
    private static Validator validator;
    private final JsonMapper mapper = JsonMapper.builder().build();

    @BeforeAll static void start() { factory = Validation.buildDefaultValidatorFactory(); validator = factory.getValidator(); }
    @AfterAll static void stop() { factory.close(); }

    private static Set<String> invalidFields(PatientRequest request) {
        return validator.validate(request).stream().map(issue -> issue.getPropertyPath().toString()).collect(Collectors.toSet());
    }

    private static int status(Runnable action) {
        return assertThrows(ResponseStatusException.class, action::run).getStatusCode().value();
    }

    @Test
    void namesFollowR2R3R4() {
        Map<String, String> valid = Map.of("  Ana  ", "Ana", "Ana\u00A0", "Ana", EMOJI.repeat(200), EMOJI.repeat(200),
                "José Núñez", "José Núñez");
        valid.forEach((input, expected) -> {
            var request = new PatientRequest(input, BIRTH, "ana@example.com");
            assertEquals(expected, request.name());
            assertTrue(invalidFields(request).isEmpty(), input);
        });
        for (String input : List.of("\u00A0", EMOJI.repeat(201), "Ana\u202EX", "Ana\u2028Demo", "Ana\tDemo", "",
                "Ana\u0000", "Ana\uD800")) {
            assertEquals(Set.of("name"), invalidFields(new PatientRequest(input, BIRTH, "ana@example.com")), input);
        }
    }

    @Test
    void emailsFollowR6() {
        Map<String, String> valid = Map.of("Ana@Example.COM", "Ana@example.com", " ana@ex.com ", "ana@ex.com",
                "ana+tag@ex.com", "ana+tag@ex.com", "ana@ejemplo.españa", "ana@ejemplo.españa");
        valid.forEach((input, expected) -> {
            var request = new PatientRequest("Ana", BIRTH, input);
            assertEquals(expected, request.email());
            assertTrue(invalidFields(request).isEmpty(), input);
        });
        for (String input : List.of("ana@localhost", "ana@[127.0.0.1]", "ana@127.0.0.1", "a\u0081b@example.com",
                "ana@exa mple.com", "ana@ex\u200B.com", "a".repeat(250) + "@ex.com")) {
            assertEquals(Set.of("email"), invalidFields(new PatientRequest("Ana", BIRTH, input)), input);
        }
    }

    @Test
    void birthDatesFollowR7() throws Exception {
        assertTrue(invalidFields(new PatientRequest("Ana", LocalDate.now(), "ana@example.com")).isEmpty());
        assertEquals(Set.of("birthDate"), invalidFields(new PatientRequest("Ana", LocalDate.now().plusDays(1), "ana@example.com")));
        String json = "{\"name\":\"Ana\",\"birth_date\":\"%s\",\"email\":\"ana@example.com\"}";
        assertEquals(LocalDate.of(2024, 2, 29), mapper.readValue(json.formatted("2024-02-29"), PatientRequest.class).birthDate());
        for (String date : List.of("0000-01-01", "1990-02-30", "1990-1-02", "02-01-1990")) {
            var error = assertThrows(JacksonException.class, () -> mapper.readValue(json.formatted(date), PatientRequest.class), date);
            assertEquals("birth_date", error.getPath().getFirst().getPropertyName());
        }
    }

    @Test
    void loneSurrogatesAreRejectedWhileReadingJson() {
        var error = assertThrows(JacksonException.class, () -> mapper.readValue(
                "{\"name\":\"Ana\\ud800\",\"birth_date\":\"1990-01-02\",\"email\":\"ana@example.com\"}", PatientRequest.class));
        assertEquals("name", error.getPath().getFirst().getPropertyName());
    }

    @Test
    void clinicalFieldsFollowR2R3R4R5() {
        assertEquals("Reflujo", InputRules.clinical("disease", "Reflujo"));
        assertEquals("Reflujo", InputRules.clinical("disease", "  Reflujo \t"));
        assertEquals("Texto #hashtag", InputRules.clinical("disease", "Texto #hashtag"));
        assertEquals("", InputRules.clinical("disease", "\u00A0"));
        assertEquals("", InputRules.clinical("disease", "No registrado."));
        assertEquals("Línea 1\nLínea 2", InputRules.clinical("disease", "Línea 1\r\nLínea 2\r"));
        assertEquals(2000, InputRules.clinical("disease", EMOJI.repeat(2000)).codePointCount(0, 4000));
        for (String input : List.of("Reflujo\u2028# nota", "# Titulo", "Linea 1\n## Sub", "Re\u200Bflujo",
                EMOJI.repeat(2001), "Dato\u0000", "Dato\uD800", "Linea\r# Titulo", "####### siete\n###### seis")) {
            assertEquals(422, status(() -> InputRules.clinical("disease", input)), input);
        }
        assertEquals(422, status(() -> HistoryMarkdown.entry("6ec12d52-872c-4d82-a6b8-235cbd99936c", "\u00A0", "No registrado.", "")));
    }

    @Test
    void routeIdsFollowR1() {
        assertEquals(1, InputRules.patientId("1"));
        assertEquals(1, InputRules.patientId("01"));
        assertEquals(Integer.MAX_VALUE, InputRules.patientId("2147483647"));
        for (String input : List.of("0", "-1", "abc", "0x1", "1e3", "2147483648", "99999999999", "", " 1", "١")) {
            assertEquals(422, status(() -> InputRules.patientId(input)), input);
        }
        assertEquals("6ec12d52-872c-4d82-a6b8-235cbd99936c", InputRules.uuid("6EC12D52-872C-4D82-A6B8-235CBD99936C", "disease_id"));
        for (String input : List.of("no-uuid", "6ec12d52872c4d82a6b8235cbd99936c", "{6ec12d52-872c-4d82-a6b8-235cbd99936c}")) {
            assertEquals(422, status(() -> InputRules.uuid(input, "disease_id")), input);
        }
    }

    @Test
    void consultationIdIsCaseInsensitive() {
        var request = new ConsultationRequest("6EC12D52-872C-4D82-A6B8-235CBD99936C", "q", "a", "b", "m", List.of());
        assertEquals("6ec12d52-872c-4d82-a6b8-235cbd99936c", request.id());
        assertTrue(validator.validate(request).isEmpty());
    }

    @Test
    void consultationAcceptsNineContextSourcesAndRejectsTen() throws Exception {
        var sources = java.util.stream.IntStream.range(0, 9)
                .mapToObj(index -> Map.<String, Object>of("patient_id", 7, "chunk_id", "fragmento-" + index)).toList();
        var request = new ConsultationRequest("6ec12d52-872c-4d82-a6b8-235cbd99936c", "q", "a", "b", "m", sources);
        var decoded = mapper.readValue(mapper.writeValueAsString(request), ConsultationRequest.class);
        assertEquals(sources, decoded.sources());
        assertTrue(validator.validate(decoded).isEmpty());

        var tooMany = new java.util.ArrayList<>(sources);
        tooMany.add(Map.of("patient_id", 7, "chunk_id", "fragmento-9"));
        var invalid = new ConsultationRequest(request.id(), "q", "a", "b", "m", tooMany);
        assertEquals(Set.of("sources"), validator.validate(invalid).stream()
                .map(issue -> issue.getPropertyPath().toString()).collect(Collectors.toSet()));
    }

    @Test
    void sourcesWithNulOrLoneSurrogateAreNotStorable() {
        assertTrue(InputRules.storable(List.of(Map.of("patient_id", 1, "text", "ok"))));
        assertEquals(false, InputRules.storable(List.of(Map.of("patient_id", 1, "text", "a\u0000b"))));
        assertEquals(false, InputRules.storable(List.of(Map.of("nested", List.of("\uDC00")))));
    }

    @Test
    void journalComparisonIgnoresTrailingSpacesAndFinalNewlines() {
        var patient = new Patient("Ana QA", BIRTH, "ana@example.com");
        var entry = new HistoryResponse.Entry("6ec12d52-872c-4d82-a6b8-235cbd99936c", "Reflujo", "", "Omeprazol");
        var journal = List.of(new HistoryResponse.Consultation("0b0e4e0e-7c5f-4a49-9d3c-1b1c0d4f8e21",
                "Primera línea\n\nTercera línea", "Sin RAG", "Con RAG\n", "modelo", "2026-11-12T10:00:00Z", List.of()));
        String canonical = HistoryMarkdown.render(patient, List.of(entry), journal);
        assertTrue(canonical.contains("\n> \n"), "El formato escrito conserva '> ' con espacio");
        String cleaned = canonical.lines().map(String::stripTrailing)
                .collect(java.util.stream.Collectors.joining("\n")).stripTrailing();
        assertEquals(List.of(entry), HistoryMarkdown.parse(patient, cleaned, journal));
        assertEquals(List.of(entry), HistoryMarkdown.parse(patient, canonical.replace("\n", "\r\n") + "\n\n", journal));
        assertEquals(422, status(() -> HistoryMarkdown.parse(patient, canonical.replace("Sin RAG", "Editado"), journal)));
        assertEquals(422, status(() -> HistoryMarkdown.parse(patient, canonical.replace("> Tercera", ">  Tercera"), journal)));
    }

    @Test
    void blankLinesAreAllowedAfterPatientId() {
        var patient = new Patient("Ana QA", BIRTH, "ana@example.com");
        var entry = new HistoryResponse.Entry("6ec12d52-872c-4d82-a6b8-235cbd99936c", "Reflujo", "", "");
        String header = HistoryMarkdown.header(patient);
        String canonical = HistoryMarkdown.render(patient, List.of(entry), List.of());
        String body = canonical.substring(header.length());
        for (String blank : List.of("", "\n", "\n\n\n", "  \n\t\n")) {
            assertEquals(List.of(entry), HistoryMarkdown.parse(patient, header + blank + body, List.of()), "[" + blank + "]");
            assertEquals(List.of(), HistoryMarkdown.parse(patient, header + blank, List.of()), "[" + blank + "]");
        }
        assertEquals(422, status(() -> HistoryMarkdown.parse(patient, header + "\nnota\n" + body, List.of())));
    }

    @Test
    void validationErrorsUseJsonNames() {
        assertEquals("birth_date", ApiExceptionHandler.jsonName("birthDate"));
        assertEquals("direct_answer", ApiExceptionHandler.jsonName("directAnswer"));
        assertEquals("rag_answer", ApiExceptionHandler.jsonName("ragAnswer"));
        assertEquals("email", ApiExceptionHandler.jsonName("email"));
    }
}
