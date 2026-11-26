package com.conkord.genai;

import tools.jackson.core.JsonParser;
import tools.jackson.core.JsonToken;
import tools.jackson.databind.DeserializationContext;
import tools.jackson.databind.ValueDeserializer;

/** Evita que JSON convierta números o booleanos en nombres o correos. */
public class StrictTextDeserializer extends ValueDeserializer<String> {

    @Override
    public String deserialize(JsonParser parser, DeserializationContext context) {
        if (parser.currentToken() != JsonToken.VALUE_STRING) {
            return (String) context.handleUnexpectedToken(String.class, parser);
        }
        String value = parser.getString();
        // Un surrogate suelto ("\ud800") no es UTF-8 válido: 422 en vez de fallar al guardar.
        if (InputRules.hasLoneSurrogate(value)) {
            throw context.weirdStringException(value, String.class, "Contiene caracteres Unicode inválidos");
        }
        return value;
    }
}
