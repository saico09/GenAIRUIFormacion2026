package com.conkord.genai;

import com.fasterxml.jackson.annotation.JsonProperty;

public record DiseaseResponse(String id, @JsonProperty("patient_id") int patientId,
        String disease, String treatment, String medication) {
    static DiseaseResponse from(int patientId, HistoryResponse.Entry entry) {
        return new DiseaseResponse(entry.id(), patientId, entry.disease(), entry.treatment(), entry.medication());
    }
}
