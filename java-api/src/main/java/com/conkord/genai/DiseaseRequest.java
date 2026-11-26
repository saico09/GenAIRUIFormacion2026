package com.conkord.genai;

import jakarta.validation.constraints.NotNull;
import tools.jackson.databind.annotation.JsonDeserialize;

/** Un registro confirmado une enfermedad, tratamiento y medicamento con un UUID; se valida en InputRules.clinical. */
public record DiseaseRequest(
        @NotNull @JsonDeserialize(using = StrictTextDeserializer.class) String disease,
        @NotNull @JsonDeserialize(using = StrictTextDeserializer.class) String treatment,
        @NotNull @JsonDeserialize(using = StrictTextDeserializer.class) String medication) {}
