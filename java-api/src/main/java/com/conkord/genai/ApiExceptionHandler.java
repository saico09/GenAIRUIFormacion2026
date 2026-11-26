package com.conkord.genai;

import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.NestedExceptionUtils;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.orm.jpa.JpaSystemException;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.transaction.TransactionSystemException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.ErrorResponse;
import tools.jackson.core.JacksonException;
import tools.jackson.core.exc.StreamConstraintsException;

@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
    public Map<String, Object> invalidFields(MethodArgumentNotValidException error) {
        // Devolvemos nombres de campo y motivos, nunca los valores recibidos.
        var details = error.getBindingResult().getFieldErrors().stream()
                .map(field -> problem(jsonName(field.getField()),
                        field.getDefaultMessage() == null ? "Dato inválido" : field.getDefaultMessage()))
                .toList();
        return Map.of("detail", details);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, Object>> invalidJson(HttpMessageNotReadableException error) {
        Throwable cause = error.getCause();
        while (cause != null && !(cause instanceof JacksonException)) cause = cause.getCause();
        if (cause instanceof StreamConstraintsException) {
            return ResponseEntity.status(HttpStatus.CONTENT_TOO_LARGE).body(Map.of("detail", "El cuerpo de la petición supera los límites permitidos"));
        }
        String field = cause instanceof JacksonException json ? json.getPath().stream()
                .map(JacksonException.Reference::getPropertyName).filter(name -> name != null)
                .collect(Collectors.joining(".")) : "";
        if (field.isEmpty()) {
            return ResponseEntity.status(HttpStatus.UNPROCESSABLE_CONTENT).body(Map.of("detail", "JSON inválido: revisa la sintaxis y el tipo de cada campo"));
        }
        String message = field.equals("birth_date") ? "Usa una fecha real con formato YYYY-MM-DD" : "Tipo o valor inválido";
        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_CONTENT).body(Map.of("detail", List.of(problem(field, message))));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    @ResponseStatus(HttpStatus.UNPROCESSABLE_CONTENT)
    public Map<String, Object> invalidParameter(MethodArgumentTypeMismatchException error) {
        return Map.of("detail", List.of(problem(jsonName(error.getName()), "Valor inválido")));
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, String>> httpError(ResponseStatusException error, HttpServletRequest request) {
        String detail = error.getReason() == null ? "No se pudo completar la operación" : error.getReason();
        if (error.getStatusCode().is5xxServerError()) {
            log.error("HTTP {} en {} {}: {}", error.getStatusCode().value(), request.getMethod(), request.getRequestURI(), detail, error);
        }
        return ResponseEntity.status(error.getStatusCode()).body(Map.of("detail", detail));
    }

    @ExceptionHandler(PessimisticLockingFailureException.class)
    public ResponseEntity<Map<String, String>> busy(PessimisticLockingFailureException error, HttpServletRequest request) {
        log.error("Bloqueo no disponible en {} {}", request.getMethod(), request.getRequestURI(), error);
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(Map.of("detail", PatientDiseaseRepository.BUSY));
    }

    // Si PostgreSQL cae a mitad de una operación, el rollback o el COMMIT fallan con la conexión cerrada.
    @ExceptionHandler(JpaSystemException.class)
    public ResponseEntity<Map<String, String>> jpaFailure(JpaSystemException error,
            HttpServletRequest request) {
        if (NestedExceptionUtils.getMostSpecificCause(error) instanceof SQLException) {
            return databaseUnavailable(error, request);
        }
        return internalError(error, request);
    }

    @ExceptionHandler({DataAccessResourceFailureException.class, TransientDataAccessResourceException.class,
            CannotCreateTransactionException.class, TransactionSystemException.class})
    public ResponseEntity<Map<String, String>> databaseUnavailable(Exception error, HttpServletRequest request) {
        log.error("PostgreSQL no disponible en {} {}", request.getMethod(), request.getRequestURI(), error);
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(Map.of("detail", "PostgreSQL no está disponible; reintenta en unos segundos"));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> internalError(Exception error, HttpServletRequest request) {
        if (error instanceof ErrorResponse response) {
            // 404/405/415 de Spring: se conservan sus cabeceras (Allow en 405).
            String detail = switch (response.getStatusCode().value()) {
                case 404 -> "Ruta no encontrada";
                case 405 -> "Método no permitido para esta ruta";
                case 415 -> "Usa Content-Type: application/json";
                default -> "Petición no disponible";
            };
            return ResponseEntity.status(response.getStatusCode()).headers(response.getHeaders()).body(Map.of("detail", detail));
        }
        log.error("Error interno en {} {}", request.getMethod(), request.getRequestURI(), error);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(Map.of("detail", "Error interno"));
    }

    private static Map<String, String> problem(String field, String message) {
        return Map.of("field", field, "message", message);
    }

    /** Los 422 nombran los campos como en el JSON (birthDate -> birth_date). */
    static String jsonName(String field) {
        return field.replaceAll("([a-z0-9])([A-Z])", "$1_$2").toLowerCase(java.util.Locale.ROOT);
    }
}
