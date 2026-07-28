package com.voicesupport.shared.web.rest;

import io.swagger.v3.oas.annotations.media.Schema;

// Sanitized REST error contract (TASK-BE-012). Serialized snake_case via the global Jackson
// config: {error_code, message, correlation_id}. The message is always a generic, client-safe
// string — never an upstream exception's raw text (no URLs, driver output or stack hints). The
// correlation_id lets a caller cross-reference the full server-side detail (TASK-BE-009).
@Schema(description = "Sanitized error contract shared by all endpoints.")
public record ErrorResponse(
        @Schema(description = "Stable error code.", example = "ERR_UPSTREAM") String errorCode,
        @Schema(description = "Generic, client-safe message.",
                example = "A required service is temporarily unavailable. Please retry shortly.") String message,
        @Schema(description = "Correlation id to cross-reference server-side detail.") String correlationId) {

    public static ErrorResponse of(String errorCode, String message, String correlationId) {
        return new ErrorResponse(errorCode, message, correlationId);
    }
}
