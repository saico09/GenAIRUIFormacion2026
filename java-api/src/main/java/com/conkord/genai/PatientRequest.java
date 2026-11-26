package com.conkord.genai;

import java.time.LocalDate;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PastOrPresent;
import jakarta.validation.constraints.Pattern;
import tools.jackson.databind.annotation.JsonDeserialize;

/** Mismas reglas que la API Python; los límites cuentan puntos de código, no UTF-16. */
public record PatientRequest(
        @NotNull(message = "El nombre es obligatorio")
        @Pattern(regexp = InputRules.NAME,
                message = "Usa entre 1 y 200 caracteres, sin tabuladores, saltos de línea ni caracteres de control o formato")
        @JsonDeserialize(using = StrictTextDeserializer.class) String name,
        @NotNull(message = "La fecha de nacimiento es obligatoria")
        @PastOrPresent(message = "La fecha de nacimiento no puede ser posterior a hoy")
        @JsonProperty("birth_date")
        @JsonDeserialize(using = BirthDateDeserializer.class) LocalDate birthDate,
        @NotNull(message = "El email es obligatorio")
        @Email(message = "Email inválido")
        @Pattern(regexp = InputRules.EMAIL_PATTERN,
                message = "Usa nombre@dominio.tld: una sola @, sin espacios ni IP y un dominio con letras tras el último punto (máximo 254)")
        @JsonDeserialize(using = StrictTextDeserializer.class) String email) {

    public PatientRequest {
        name = InputRules.trim(name);
        email = InputRules.email(email);
    }
}
