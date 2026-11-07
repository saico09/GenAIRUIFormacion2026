package com.conkord.genai;

import java.util.List;

import jakarta.validation.Valid;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import java.nio.charset.StandardCharsets;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
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
    private final PatientHistoryService histories;

    public PatientController(PatientRepository patients, PatientHistoryService histories) {
        this.patients = patients;
        this.histories = histories;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public PatientResponse create(@Valid @RequestBody PatientRequest input) {
        return histories.create(input);
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
    public PatientResponse update(@PathVariable Integer id, @Valid @RequestBody PatientRequest input) {
        return histories.update(id, input);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Integer id) {
        histories.delete(id);
    }

    @GetMapping("/{id}/history")
    public HistoryResponse history(@PathVariable Integer id) { return histories.get(id); }

    @GetMapping("/{id}/history.md")
    public ResponseEntity<String> downloadHistory(@PathVariable Integer id) {
        HistoryResponse history = histories.get(id);
        return ResponseEntity.ok().contentType(new MediaType("text", "markdown", StandardCharsets.UTF_8))
                .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.attachment().filename(history.filename()).build().toString())
                .body(history.markdown());
    }

    @PutMapping("/{id}/history")
    public HistoryResponse replaceHistory(@PathVariable Integer id, @Valid @RequestBody HistoryRequest.Replace input) {
        return histories.replace(id, input);
    }

    @PostMapping("/{id}/history/entries")
    @ResponseStatus(HttpStatus.CREATED)
    public HistoryResponse appendHistory(@PathVariable Integer id, @Valid @RequestBody HistoryRequest.Append input) {
        return histories.append(id, input);
    }

    @PostMapping("/{id}/consultations")
    public ResponseEntity<HistoryResponse> addConsultation(@PathVariable Integer id,
            @Valid @RequestBody ConsultationRequest input) {
        var saved = histories.consult(id, input);
        return ResponseEntity.status(saved.created() ? HttpStatus.CREATED : HttpStatus.OK).body(saved.history());
    }

    @GetMapping("/{id}/consultations/{consultationId}")
    public HistoryResponse.Consultation consultation(@PathVariable Integer id, @PathVariable String consultationId) {
        return histories.getConsultation(id, consultationId);
    }

    private Patient findPatient(Integer id) {
        return patients.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Paciente no encontrado"));
    }
}
