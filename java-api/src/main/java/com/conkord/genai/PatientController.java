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

/** Los IDs llegan como texto y se validan como en Python; las rutas conservan {id} para Loki y Prometheus. */
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
    public PatientResponse get(@PathVariable String id) {
        return PatientResponse.from(findPatient(InputRules.patientId(id)));
    }

    @PutMapping("/{id}")
    public PatientResponse update(@PathVariable String id, @Valid @RequestBody PatientRequest input) {
        return histories.update(InputRules.patientId(id), input);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        histories.delete(InputRules.patientId(id));
    }

    @GetMapping("/{id}/history")
    public HistoryResponse history(@PathVariable String id) { return histories.get(InputRules.patientId(id)); }

    @GetMapping("/{id}/diseases")
    public List<DiseaseResponse> diseases(@PathVariable String id) { return histories.listDiseases(InputRules.patientId(id)); }

    @GetMapping("/{id}/diseases/{diseaseId}")
    public DiseaseResponse disease(@PathVariable String id, @PathVariable String diseaseId) {
        int patientId = InputRules.patientId(id);
        return histories.getDisease(patientId, InputRules.uuid(diseaseId, "disease_id"));
    }

    @PostMapping("/{id}/diseases")
    @ResponseStatus(HttpStatus.CREATED)
    public DiseaseResponse addDisease(@PathVariable String id, @Valid @RequestBody DiseaseRequest input) {
        return histories.addDisease(InputRules.patientId(id), input);
    }

    @PutMapping("/{id}/diseases/{diseaseId}")
    public DiseaseResponse updateDisease(@PathVariable String id, @PathVariable String diseaseId,
            @Valid @RequestBody DiseaseRequest input) {
        int patientId = InputRules.patientId(id);
        return histories.updateDisease(patientId, InputRules.uuid(diseaseId, "disease_id"), input);
    }

    @DeleteMapping("/{id}/diseases/{diseaseId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteDisease(@PathVariable String id, @PathVariable String diseaseId) {
        int patientId = InputRules.patientId(id);
        histories.deleteDisease(patientId, InputRules.uuid(diseaseId, "disease_id"));
    }

    @GetMapping("/{id}/history.md")
    public ResponseEntity<String> downloadHistory(@PathVariable String id) {
        HistoryResponse history = histories.get(InputRules.patientId(id));
        return ResponseEntity.ok().contentType(new MediaType("text", "markdown", StandardCharsets.UTF_8))
                .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.attachment().filename(history.filename()).build().toString())
                .body(history.markdown());
    }

    @PutMapping("/{id}/history")
    public HistoryResponse replaceHistory(@PathVariable String id, @Valid @RequestBody HistoryRequest.Replace input) {
        return histories.replace(InputRules.patientId(id), input);
    }

    @PostMapping("/{id}/history/entries")
    @ResponseStatus(HttpStatus.CREATED)
    public HistoryResponse appendHistory(@PathVariable String id, @Valid @RequestBody HistoryRequest.Append input) {
        return histories.append(InputRules.patientId(id), input);
    }

    @PostMapping("/{id}/consultations")
    public ResponseEntity<HistoryResponse> addConsultation(@PathVariable String id,
            @Valid @RequestBody ConsultationRequest input) {
        var saved = histories.consult(InputRules.patientId(id), input);
        return ResponseEntity.status(saved.created() ? HttpStatus.CREATED : HttpStatus.OK).body(saved.history());
    }

    @GetMapping("/{id}/consultations/{consultationId}")
    public HistoryResponse.Consultation consultation(@PathVariable String id, @PathVariable String consultationId) {
        int patientId = InputRules.patientId(id);
        return histories.getConsultation(patientId, InputRules.uuid(consultationId, "consultation_id"));
    }

    private Patient findPatient(int id) {
        return patients.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Paciente no encontrado"));
    }
}
