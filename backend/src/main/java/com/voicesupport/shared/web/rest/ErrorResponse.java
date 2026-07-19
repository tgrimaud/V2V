package com.voicesupport.shared.web.rest;

// Sanitized REST error contract (TASK-BE-012). Serialized snake_case via the global Jackson
// config: {error_code, message, correlation_id}. The message is always a generic, client-safe
// string — never an upstream exception's raw text (no URLs, driver output or stack hints). The
// correlation_id lets a caller cross-reference the full server-side detail (TASK-BE-009).
public record ErrorResponse(String errorCode, String message, String correlationId) {

    public static ErrorResponse of(String errorCode, String message, String correlationId) {
        return new ErrorResponse(errorCode, message, correlationId);
    }
}
