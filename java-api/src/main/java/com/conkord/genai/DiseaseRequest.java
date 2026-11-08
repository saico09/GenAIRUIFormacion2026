package com.conkord.genai;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import tools.jackson.databind.annotation.JsonDeserialize;

/** Un registro confirmado une enfermedad, tratamiento y medicamento con un UUID. */
public record DiseaseRequest(
        @NotNull @Size(max = 2000) @JsonDeserialize(using = StrictTextDeserializer.class) String disease,
        @NotNull @Size(max = 2000) @JsonDeserialize(using = StrictTextDeserializer.class) String treatment,
        @NotNull @Size(max = 2000) @JsonDeserialize(using = StrictTextDeserializer.class) String medication) {}
