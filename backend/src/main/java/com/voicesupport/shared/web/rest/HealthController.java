package com.voicesupport.shared.web.rest;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
@Tag(name = "Health", description = "Service liveness.")
public class HealthController {

    private static final String SERVICE_NAME = "voice-support-backend";

    @GetMapping("/health")
    @Operation(summary = "Health check",
            description = "Returns a static UP status while the service is running.")
    public HealthResponse health() {
        return HealthResponse.up(SERVICE_NAME);
    }

    @Schema(description = "Service liveness status.")
    public record HealthResponse(
            @Schema(description = "Liveness status.", example = "UP") String status,
            @Schema(description = "Service name.", example = "voice-support-backend") String service) {
        static HealthResponse up(String service) {
            return new HealthResponse("UP", service);
        }
    }
}
