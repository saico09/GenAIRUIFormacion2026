package com.conkord.genai;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import tools.jackson.databind.annotation.JsonDeserialize;
import java.util.List;
import java.util.Map;

/** El texto consultado y las respuestas se guardan como conversación, no como diagnóstico. */
public record ConsultationRequest(
        @NotBlank @Pattern(regexp = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        @JsonDeserialize(using = StrictTextDeserializer.class) String id,
        @NotBlank @Size(max = 6000) @JsonDeserialize(using = StrictTextDeserializer.class) String question,
        @NotBlank @Size(max = 16000) @JsonProperty("direct_answer")
        @JsonDeserialize(using = StrictTextDeserializer.class) String directAnswer,
        @NotBlank @Size(max = 16000) @JsonProperty("rag_answer")
        @JsonDeserialize(using = StrictTextDeserializer.class) String ragAnswer,
        @NotBlank @Size(max = 200) @JsonDeserialize(using = StrictTextDeserializer.class) String model,
        @NotNull @Size(max = 3) List<Map<String, Object>> sources) {}
