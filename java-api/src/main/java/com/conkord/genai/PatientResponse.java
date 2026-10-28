package com.conkord.genai;

import java.time.LocalDate;

import com.fasterxml.jackson.annotation.JsonProperty;

public record PatientResponse(Integer id, String name,
        @JsonProperty("birth_date") LocalDate birthDate, String email) {

    public static PatientResponse from(Patient patient) {
        return new PatientResponse(patient.getId(), patient.getName(),
                patient.getBirthDate(), patient.getEmail());
    }
}
