package com.conkord.genai;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import tools.jackson.databind.annotation.JsonDeserialize;

public final class HistoryRequest {
    private HistoryRequest() {}

    public record Replace(
            @NotNull @Pattern(regexp = "[0-9a-f]{64}")
            @JsonDeserialize(using = StrictTextDeserializer.class) String revision,
            @NotNull @Size(max = 1048576)
            @JsonDeserialize(using = StrictTextDeserializer.class) String markdown,
            @NotNull @AssertTrue @JsonDeserialize(using = StrictBooleanDeserializer.class) Boolean confirmed) {}

    public record Append(
            @NotNull @Pattern(regexp = "[0-9a-f]{64}")
            @JsonDeserialize(using = StrictTextDeserializer.class) String revision,
            @NotNull @Size(max = 2000) @JsonDeserialize(using = StrictTextDeserializer.class) String disease,
            @NotNull @Size(max = 2000) @JsonDeserialize(using = StrictTextDeserializer.class) String treatment,
            @NotNull @Size(max = 2000) @JsonDeserialize(using = StrictTextDeserializer.class) String medication,
            @NotNull @AssertTrue @JsonDeserialize(using = StrictBooleanDeserializer.class) Boolean confirmed) {}
}
