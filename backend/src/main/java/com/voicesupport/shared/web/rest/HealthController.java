package com.voicesupport.shared.web.rest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class HealthController {

    private static final String SERVICE_NAME = "voice-support-backend";

    @GetMapping("/health")
    public HealthResponse health() {
        return HealthResponse.up(SERVICE_NAME);
    }

    public record HealthResponse(String status, String service) {
        static HealthResponse up(String service) {
            return new HealthResponse("UP", service);
        }
    }
}
