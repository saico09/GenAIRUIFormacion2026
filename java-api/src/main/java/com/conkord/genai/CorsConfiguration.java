package com.conkord.genai;

import java.util.Arrays;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfiguration implements WebMvcConfigurer {

    private final String[] allowedOrigins;

    public CorsConfiguration(@Value("${app.cors.allowed-origins}") String origins) {
        allowedOrigins = Arrays.stream(origins.split(","))
                .map(String::strip)
                .filter(origin -> !origin.isEmpty())
                .distinct()
                .toArray(String[]::new);
        if (Arrays.stream(allowedOrigins).anyMatch(origin -> origin.contains("*"))) {
            throw new IllegalArgumentException("APP_CORS_ALLOWED_ORIGINS requiere origenes explicitos, sin comodines");
        }
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**")
                .allowedOrigins(allowedOrigins)
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
                .allowedHeaders("Content-Type", "X-Request-ID")
                .exposedHeaders("X-Request-ID")
                .allowCredentials(false);
    }
}
