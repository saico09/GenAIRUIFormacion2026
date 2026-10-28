package com.conkord.genai;

import java.util.List;

import jakarta.validation.Valid;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/patients")
public class PatientController {

    private final PatientRepository patients;

    public PatientController(PatientRepository patients) {
        this.patients = patients;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public PatientResponse create(@Valid @RequestBody PatientRequest input) {
        Patient patient = new Patient(input.name(), input.birthDate(), input.email());
        return PatientResponse.from(patients.save(patient));
    }

    @GetMapping
    public List<PatientResponse> list() {
        return patients.findAll(Sort.by("id")).stream().map(PatientResponse::from).toList();
    }

    @GetMapping("/{id}")
    public PatientResponse get(@PathVariable Integer id) {
        return PatientResponse.from(findPatient(id));
    }

    @PutMapping("/{id}")
    @Transactional
    public PatientResponse update(@PathVariable Integer id, @Valid @RequestBody PatientRequest input) {
        Patient patient = findPatient(id);
        // JPA guarda los tres cambios al confirmar esta transacción.
        patient.updateDetails(input.name(), input.birthDate(), input.email());
        return PatientResponse.from(patient);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Transactional
    public void delete(@PathVariable Integer id) {
        patients.delete(findPatient(id));
    }

    private Patient findPatient(Integer id) {
        return patients.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Paciente no encontrado"));
    }
}
