package com.conkord.genai;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

import org.springframework.web.server.ResponseStatusException;

/** Python escribe y lee el mismo formato: un cambio de texto aquí debe repetirse allá. */
final class HistoryMarkdown {
    static final int MAX_BYTES = 1048576;
    static final int MAX_ENTRIES = 50;
    private static final String JOURNAL_HEADING = "\n## Consultas registradas\n";
    private static final Pattern UUID_PATTERN = Pattern.compile("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");
    private static final String ENTRY_HEADING = "\n## Registro ";
    private static final String DISEASE_HEADING = "\n\n### Enfermedad\n";
    private static final String TREATMENT_HEADING = "\n\n### Tratamiento\n";
    private static final String MEDICATION_HEADING = "\n\n### Medicamento\n";
    private static final List<String> JSON_FIELDS = List.of("disease", "treatment", "medication");
    private static final List<String> SECTIONS = List.of("Enfermedad", "Tratamiento", "Medicamento");

    private HistoryMarkdown() {}

    static String header(Patient patient) {
        return "# Historia clínica ficticia — " + patient.getName()
                + "\n\nDatos ficticios para la formación.\n\npatient_id: " + patient.getId() + "\n";
    }

    static String render(Patient patient, List<HistoryResponse.Entry> entries, List<HistoryResponse.Consultation> journal) {
        StringBuilder text = new StringBuilder(header(patient));
        for (var entry : entries) {
            text.append("\n## Registro ").append(entry.id()).append("\n\n### Enfermedad\n")
                    .append(shown(entry.disease())).append("\n\n### Tratamiento\n")
                    .append(shown(entry.treatment())).append("\n\n### Medicamento\n")
                    .append(shown(entry.medication())).append('\n');
        }
        return text.append(renderJournal(journal)).toString();
    }

    static String renderJournal(List<HistoryResponse.Consultation> journal) {
        if (journal.isEmpty()) return "";
        StringBuilder text = new StringBuilder(JOURNAL_HEADING)
                .append("\nConversaciones guardadas automáticamente. La nota describe lo reportado; las respuestas de IA no son diagnósticos confirmados.\n");
        for (var item : journal) {
            text.append("\n### Consulta ").append(item.id()).append("\n\nFecha UTC: ").append(item.createdAt())
                    .append("\n\nModelo: ").append(item.model()).append("\n\n#### Nota reportada\n")
                    .append(quoted(item.question())).append("\n\n#### Respuesta sin RAG\n")
                    .append(quoted(item.directAnswer())).append("\n\n#### Respuesta con RAG\n")
                    .append(quoted(item.ragAnswer())).append('\n');
        }
        return text.toString();
    }

    private static String quoted(String text) { return "> " + text.replace("\r\n", "\n").replace('\r', '\n').replace("\n", "\n> "); }

    private static String shown(String value) { return value.isEmpty() ? InputRules.EMPTY : value; }

    static List<HistoryResponse.Entry> parse(Patient patient, String markdown, List<HistoryResponse.Consultation> journal) {
        checkSize(markdown);
        String normalized = markdown.replace("\r\n", "\n");
        String header = header(patient);
        if (!normalized.startsWith(header)) throw InputRules.invalid("El título y patient_id deben conservar el propietario del informe");
        String body = skipBlankLines(normalized.substring(header.length()));
        int journalStart = body.indexOf(JOURNAL_HEADING);
        if (journalStart >= 0) {
            if (!comparableJournal(body.substring(journalStart)).equals(comparableJournal(renderJournal(journal)))) {
                throw InputRules.invalid("Las consultas automáticas son históricas; edita sólo los registros confirmados antes de Consultas registradas");
            }
            body = body.substring(0, journalStart);
        } else if (!journal.isEmpty()) {
            throw InputRules.invalid("Conserva la sección Consultas registradas sin cambios");
        }
        var entries = new ArrayList<HistoryResponse.Entry>();
        var ids = new HashSet<String>();
        int offset = 0;
        while (offset < body.length()) {
            if (entries.size() == MAX_ENTRIES) throw InputRules.invalid("La historia admite como máximo 50 registros");
            if (!body.startsWith(ENTRY_HEADING, offset)) throw InputRules.invalid("Estructura Markdown inválida");
            int idStart = offset + ENTRY_HEADING.length();
            int idEnd = idStart + 36;
            if (idEnd > body.length() || !body.startsWith(DISEASE_HEADING, idEnd)) {
                throw InputRules.invalid("Usa Registro, Enfermedad, Tratamiento y Medicamento con sus encabezados originales");
            }
            String id = body.substring(idStart, idEnd);
            if (!UUID_PATTERN.matcher(id).matches() || !ids.add(id)) throw InputRules.invalid("Cada registro requiere un UUID válido y único");
            int diseaseStart = idEnd + DISEASE_HEADING.length();
            int nextEntry = body.indexOf(ENTRY_HEADING, diseaseStart);
            int end = nextEntry < 0 ? body.length() : nextEntry;
            int treatment = sectionOffset(body, TREATMENT_HEADING, diseaseStart, end);
            int treatmentStart = treatment + TREATMENT_HEADING.length();
            int medication = sectionOffset(body, MEDICATION_HEADING, treatmentStart, end);
            // Los separadores se recorren una vez: un informe mal formado no provoca backtracking.
            entries.add(entry(id, SECTIONS, body.substring(diseaseStart, treatment),
                    body.substring(treatmentStart, medication),
                    body.substring(medication + MEDICATION_HEADING.length(), end)));
            offset = end;
        }
        return entries;
    }

    /** Como en Python, tras "patient_id: N" se admiten líneas en blanco o con espacios/tabuladores. */
    private static String skipBlankLines(String body) {
        int start = 0;
        while (start < body.length()) {
            int lineEnd = body.indexOf('\n', start);
            int end = lineEnd < 0 ? body.length() : lineEnd;
            for (int i = start; i < end; i++) {
                if (body.charAt(i) != ' ' && body.charAt(i) != '\t') return "\n" + body.substring(start);
            }
            start = lineEnd < 0 ? body.length() : lineEnd + 1;
        }
        return "";
    }

    /** Un editor puede quitar espacios finales (líneas "> ") o el salto final: se compara sin ellos. */
    static String comparableJournal(String text) {
        StringBuilder result = new StringBuilder(text.length());
        for (String line : text.replace("\r\n", "\n").split("\n", -1)) {
            int end = line.length();
            while (end > 0 && (line.charAt(end - 1) == ' ' || line.charAt(end - 1) == '\t')) end--;
            result.append(line, 0, end).append('\n');
        }
        int end = result.length();
        while (end > 0 && result.charAt(end - 1) == '\n') end--;
        return result.substring(0, end);
    }

    private static int sectionOffset(String body, String heading, int from, int end) {
        int offset = body.indexOf(heading, from);
        if (offset < 0 || offset + heading.length() > end) {
            throw InputRules.invalid("Usa Registro, Enfermedad, Tratamiento y Medicamento con sus encabezados originales");
        }
        return offset;
    }

    static HistoryResponse.Entry entry(String id, String disease, String treatment, String medication) {
        return entry(id, JSON_FIELDS, disease, treatment, medication);
    }

    private static HistoryResponse.Entry entry(String id, List<String> labels, String disease, String treatment, String medication) {
        String d = InputRules.clinical(labels.get(0), disease);
        String t = InputRules.clinical(labels.get(1), treatment);
        String m = InputRules.clinical(labels.get(2), medication);
        if (d.isEmpty() && t.isEmpty() && m.isEmpty()) throw InputRules.invalid("Un registro necesita al menos un campo con información");
        return new HistoryResponse.Entry(id, d, t, m);
    }

    static String filename(Patient patient) {
        String slug = Normalizer.normalize(patient.getName(), Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "").toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", "-")
                .replaceAll("(^-)|(-$)", "");
        if (slug.length() > 80) slug = slug.substring(0, 80).replaceAll("-$", "");
        if (slug.isEmpty()) slug = "paciente";
        return "paciente-" + patient.getId() + "-" + slug + ".md";
    }

    static String revision(String markdown) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(markdown.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 no disponible", impossible);
        }
    }

    /** UTF-8 estricto: un byte inválido es un archivo dañado, no un error de disco. */
    static String decode(byte[] bytes) {
        try {
            return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
        } catch (CharacterCodingException error) {
            throw InputRules.invalid("El informe no es texto UTF-8 válido");
        }
    }

    static void checkSize(String text) {
        if (text == null || text.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES) {
            throw InputRules.invalid("El Markdown admite como máximo 1 MiB UTF-8");
        }
    }

    static boolean isInvalid(ResponseStatusException error) { return error.getStatusCode().value() == 422; }
}
