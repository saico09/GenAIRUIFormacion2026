package com.conkord.genai;

import java.util.List;
import com.fasterxml.jackson.annotation.JsonProperty;

public record HistoryResponse(@JsonProperty("patient_id") int patientId, String filename,
        String revision, String markdown, List<Entry> entries) {
    public record Entry(String id, String disease, String treatment, String medication) {}
}
