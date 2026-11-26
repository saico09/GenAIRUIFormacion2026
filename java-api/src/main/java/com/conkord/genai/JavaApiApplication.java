package com.conkord.genai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.jackson.autoconfigure.JsonFactoryBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import tools.jackson.core.StreamReadConstraints;

@SpringBootApplication
public class JavaApiApplication {

    private static final Logger log = LoggerFactory.getLogger(JavaApiApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(JavaApiApplication.class, args);
    }

    @Bean
    ApplicationRunner verifyDatabase(PatientRepository patients) {
        // Registra sólo el conteo, nunca datos de pacientes.
        return args -> log.info("Tabla public.patients compartida accesible: {} filas", patients.count());
    }

    @Bean
    JsonFactoryBuilderCustomizer requestLimits() {
        // Cubre también los cuerpos chunked (sin Content-Length), que HttpLoggingFilter no puede medir antes de leer.
        return factory -> factory.streamReadConstraints(StreamReadConstraints.builder()
                .maxDocumentLength(HttpLoggingFilter.MAX_REQUEST_BYTES)
                .maxStringLength(2 * 1024 * 1024)
                .maxNestingDepth(100)
                .build());
    }
}
