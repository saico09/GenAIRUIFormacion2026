package com.conkord.genai;

import java.util.Collection;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Reglas de entrada comunes con la API Python: ambas deben aceptar y rechazar lo mismo. */
final class InputRules {
    private static final String FORBIDDEN = "\\p{Cc}\\p{Cf}\\p{Zl}\\p{Zp}\\p{Cs}";
    private static final String SPACES = "\\s\\p{Z}";
    // Java cuenta puntos de código en las clases de caracteres: un emoji vale 1, no 2.
    static final String NAME = "[^" + FORBIDDEN + "]{1,200}";
    static final String EMAIL_PATTERN = "(?=.{1,254}\\z)[^@" + SPACES + FORBIDDEN + "]+@[^@\\[" + SPACES + FORBIDDEN + "]*\\."
            + "[^.@\\[" + SPACES + FORBIDDEN + "]*\\p{L}[^.@\\[" + SPACES + FORBIDDEN + "]*";
    static final String EMPTY = "No registrado.";
    private static final int CLINICAL_MAX = 2000;
    private static final Pattern DIGITS = Pattern.compile("[0-9]{1,10}");
    private static final Pattern UUID_TEXT = Pattern.compile(
            "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
    // (?d): sólo LF separa líneas, como en Python.
    private static final Pattern HEADING = Pattern.compile("(?dm)^#{1,6}(?:[ \\t]|$)");

    private InputRules() {}

    /** Recorte común con Python; a diferencia de String.strip(), quita U+00A0. */
    static String trim(String value) {
        if (value == null) return null;
        int start = 0, end = value.length();
        while (start < end && edgeSpace(value.charAt(start))) start++;
        while (end > start && edgeSpace(value.charAt(end - 1))) end--;
        return value.substring(start, end);
    }

    private static boolean edgeSpace(char c) {
        return c == ' ' || c == '\t' || c == '\n' || c == '\r' || Character.getType(c) == Character.SPACE_SEPARATOR;
    }

    /** El dominio no distingue mayúsculas; la parte local se conserva tal cual. */
    static String email(String value) {
        String text = trim(value);
        if (text == null) return null;
        int separator = text.lastIndexOf('@');
        return separator < 0 ? text : text.substring(0, separator + 1) + text.substring(separator + 1).toLowerCase(Locale.ROOT);
    }

    static int patientId(String value) {
        if (value != null && DIGITS.matcher(value).matches()) {
            long id = Long.parseLong(value);
            if (id >= 1 && id <= Integer.MAX_VALUE) return (int) id;
        }
        throw invalid("patient_id debe ser un número entero entre 1 y 2147483647");
    }

    static String uuid(String value, String field) {
        if (value == null || !UUID_TEXT.matcher(value).matches()) throw invalid(field + " debe ser un UUID");
        return value.toLowerCase(Locale.ROOT);
    }

    static String clinical(String field, String value) {
        if (value == null) throw invalid(field + ": debe ser texto");
        if (hasLoneSurrogate(value)) throw invalid(field + ": contiene caracteres Unicode inválidos");
        String text = trim(value.replace("\r\n", "\n").replace('\r', '\n'));
        if (text.equals(EMPTY)) return "";
        if (text.codePoints().anyMatch(c -> c != '\n' && c != '\t' && forbidden(c))) {
            throw invalid(field + ": no admite caracteres de control, de formato ni separadores Unicode");
        }
        if (text.codePointCount(0, text.length()) > CLINICAL_MAX) throw invalid(field + ": admite hasta 2000 caracteres");
        if (HEADING.matcher(text).find()) throw invalid(field + ": ninguna línea puede empezar como encabezado Markdown (#)");
        return text;
    }

    private static boolean forbidden(int c) {
        int type = Character.getType(c);
        return type == Character.CONTROL || type == Character.FORMAT
                || type == Character.LINE_SEPARATOR || type == Character.PARAGRAPH_SEPARATOR;
    }

    static boolean hasLoneSurrogate(String value) {
        return value.codePoints().anyMatch(c -> Character.getType(c) == Character.SURROGATE);
    }

    /** PostgreSQL (TEXT/jsonb) no guarda U+0000 ni surrogates sueltos. */
    static boolean storable(Object value) {
        if (value instanceof String text) return text.indexOf('\u0000') < 0 && !hasLoneSurrogate(text);
        if (value instanceof Map<?, ?> map) {
            return map.entrySet().stream().allMatch(item -> storable(item.getKey()) && storable(item.getValue()));
        }
        if (value instanceof Collection<?> items) return items.stream().allMatch(InputRules::storable);
        return true;
    }

    static ResponseStatusException invalid(String message) {
        return new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT, message);
    }
}
