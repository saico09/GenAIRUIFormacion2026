package com.conkord.genai;

import java.util.List;
import java.util.Map;
import com.fasterxml.jackson.annotation.JsonProperty;

public record HistoryResponse(@JsonProperty("patient_id") int patientId, String filename,
        String revision, String markdown, List<Entry> entries, List<Consultation> consultations) {
    public record Entry(String id, String disease, String treatment, String medication) {}
    public record Consultation(String id, String question,
            @JsonProperty("direct_answer") String directAnswer,
            @JsonProperty("rag_answer") String ragAnswer, String model,
            @JsonProperty("created_at") String createdAt, List<Map<String, Object>> sources) {}
}
