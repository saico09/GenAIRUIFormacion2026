package com.conkord.genai;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.validation.Validation;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class ValidationRegressionTest {
    private static final String ID = "6ec12d52-872c-4d82-a6b8-235cbd99936c";
    private static final Patient PATIENT = new Patient("Ana QA", LocalDate.of(1990, 1, 2), "ana@example.com");
    private static final String HEADER = "# Historia clínica ficticia — Ana QA\n\nDatos ficticios para la formación.\n\npatient_id: null\n";

    static String record(String id, String disease, String treatment, String medication) {
        return "\n## Registro " + id + "\n\n### Enfermedad\n" + disease
                + "\n\n### Tratamiento\n" + treatment + "\n\n### Medicamento\n" + medication + "\n";
    }

    private List<HistoryResponse.Entry> parse(String body) {
        return HistoryMarkdown.parse(PATIENT, HEADER + body, List.of());
    }

    @Test
    void markdownPreservesFieldsAndCrLf() {
        String body = record(ID, "Reflujo\nNotas con tildes y # dentro de una línea.", "\tPlan\nsegunda línea", "No registrado.");
        var entries = HistoryMarkdown.parse(PATIENT, (HEADER + body).replace("\n", "\r\n"), List.of());
        assertEquals(List.of(new HistoryResponse.Entry(ID, "Reflujo\nNotas con tildes y # dentro de una línea.",
                "Plan\nsegunda línea", "")), entries);
        assertTrue(parse("").isEmpty());
    }

    @Test
    void markdownRejectsBrokenStructureAndDuplicateIds() {
        String valid = record(ID, "Reflujo", "Plan", "Medicamento");
        for (String broken : List.of(valid + valid, "texto" + valid,
                valid.replace("### Tratamiento", "### Otra sección"),
                valid.replace(ID, ID.toUpperCase()),
                valid.replace(ID, "no-es-un-uuid"),
                valid.replace("Reflujo", "### Encabezado no permitido"),
                record(ID, "No registrado.", "No registrado.", "No registrado."))) {
            var error = assertThrows(ResponseStatusException.class, () -> parse(broken));
            assertEquals(422, error.getStatusCode().value());
        }
    }

    @Test
    void markdownKeepsRecordAndFieldLimits() {
        StringBuilder body = new StringBuilder();
        for (int index = 0; index < 50; index++) {
            body.append(record(new UUID(0, index + 1).toString(), "x".repeat(2000), "Plan", ""));
        }
        assertEquals(50, parse(body.toString()).size());
        assertThrows(ResponseStatusException.class, () -> parse(body + record(ID, "Exceso", "", "")));
        assertThrows(ResponseStatusException.class, () -> parse(record(ID, "x".repeat(2001), "", "")));
    }

    @Test
    void malformedLargeMarkdownDoesNotBacktrack() {
        String malformed = "\n## Registro " + ID + "\n\n### Enfermedad\nReflujo"
                + "\n\n### Tratamiento\nx".repeat(24000);
        assertTimeoutPreemptively(Duration.ofSeconds(2), () ->
                assertEquals(422, assertThrows(ResponseStatusException.class, () -> parse(malformed)).getStatusCode().value()));
    }

    @Test
    void emailValidatorKeepsNormalizationAndRejectsMalformedAddresses() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var valid = new PatientRequest(" Ana ", LocalDate.of(1990, 1, 2), " Ana@EXAMPLE.COM ");
            assertEquals("Ana", valid.name());
            assertEquals("Ana@example.com", valid.email());
            assertTrue(validator.validate(valid).isEmpty());
            for (String email : List.of("ana@localhost", "ana@a..b", "a@@b.c", "a@example.com invalid",
                    "\"a@b\"@example.com", "ana@example.com.", "ana@.com", "@example.com", "ana@example.")) {
                var invalid = new PatientRequest("Ana", LocalDate.of(1990, 1, 2), email);
                assertTrue(validator.validate(invalid).stream().anyMatch(issue -> issue.getPropertyPath().toString().equals("email")), email);
            }
        }
    }

    @Test
    void longInvalidEmailDoesNotBacktrack() {
        Pattern current = Pattern.compile(InputRules.EMAIL_PATTERN);
        String malformed = "local@" + "a.".repeat(30000) + " invalid";
        String digits = "local@" + "1.".repeat(30000) + "1";
        assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
            assertFalse(current.matcher(malformed).matches());
            assertFalse(current.matcher(digits).matches());
        });
    }
}
