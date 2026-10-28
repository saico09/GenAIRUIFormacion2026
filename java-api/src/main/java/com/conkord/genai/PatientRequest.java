package com.conkord.genai;

import java.time.LocalDate;
import java.util.Locale;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import tools.jackson.databind.annotation.JsonDeserialize;

public record PatientRequest(
        @NotBlank @Size(max = 200)
        @JsonDeserialize(using = StrictTextDeserializer.class) String name,
        @NotNull @JsonProperty("birth_date")
        @JsonDeserialize(using = BirthDateDeserializer.class) LocalDate birthDate,
        @NotBlank @Email @Size(max = 254)
        @Pattern(regexp = ".+@[^@\\s]+\\.[^@\\s]+", message = "El dominio del email debe incluir un punto")
        @JsonDeserialize(using = StrictTextDeserializer.class) String email) {

    public PatientRequest {
        if (name != null) {
            name = name.strip();
        }
        if (email != null) {
            email = email.strip();
            // El dominio no distingue mayúsculas; conservamos la parte anterior a @.
            int separator = email.lastIndexOf('@');
            if (separator >= 0) {
                email = email.substring(0, separator + 1)
                        + email.substring(separator + 1).toLowerCase(Locale.ROOT);
            }
        }
    }
}
