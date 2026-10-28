package com.conkord.genai;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
    public Map<String, Object> invalidFields(MethodArgumentNotValidException error) {
        // Devolvemos nombres de campo y motivos, nunca los valores recibidos.
        var details = error.getBindingResult().getFieldErrors().stream()
                .map(field -> Map.of("field", field.getField().equals("birthDate") ? "birth_date" : field.getField(),
                        "message", field.getDefaultMessage() == null ? "Dato inválido" : field.getDefaultMessage()))
                .toList();
        return Map.of("detail", details);
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class})
    @ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
    public Map<String, String> invalidJson() {
        return Map.of("detail", "Datos inválidos: revisa los tipos y la fecha YYYY-MM-DD");
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, String>> httpError(ResponseStatusException error) {
        String detail = error.getReason() == null ? "No se pudo completar la operación" : error.getReason();
        return ResponseEntity.status(error.getStatusCode()).body(Map.of("detail", detail));
    }
}
