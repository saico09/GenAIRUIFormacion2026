package com.conkord.genai;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;

import tools.jackson.core.JsonParser;
import tools.jackson.core.JsonToken;
import tools.jackson.databind.DeserializationContext;
import tools.jackson.databind.ValueDeserializer;

/** Acepta solo texto YYYY-MM-DD de una fecha real, igual que la API Python. */
public class BirthDateDeserializer extends ValueDeserializer<LocalDate> {

    @Override
    public LocalDate deserialize(JsonParser parser, DeserializationContext context) {
        if (parser.currentToken() != JsonToken.VALUE_STRING) {
            return (LocalDate) context.handleUnexpectedToken(LocalDate.class, parser);
        }
        String value = parser.getString();
        if (!value.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}")) {
            throw context.weirdStringException(value, LocalDate.class, "Usa una fecha YYYY-MM-DD");
        }
        try {
            LocalDate date = LocalDate.parse(value);
            if (date.getYear() == 0) {
                throw context.weirdStringException(value, LocalDate.class, "El año debe ser mayor a cero");
            }
            return date;
        } catch (DateTimeParseException error) {
            throw context.weirdStringException(value, LocalDate.class, "La fecha no existe");
        }
    }
}
