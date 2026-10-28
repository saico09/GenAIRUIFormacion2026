package com.conkord.genai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JavaApiApplication {

    private static final Logger log = LoggerFactory.getLogger(JavaApiApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(JavaApiApplication.class, args);
    }

    @Bean
    ApplicationRunner verifyDatabase(PatientRepository patients) {
        // Lee solo el esquema java; registra el conteo, nunca datos de pacientes.
        return args -> log.info("Tabla java.patients accesible: {} filas", patients.count());
    }

}
