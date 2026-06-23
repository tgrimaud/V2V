package com.voicesupport.infrastructure.adapter.in.rest;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.UUID;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ErrorResponse> handleMissingParam(MissingServletRequestParameterException ex) {
        String correlationId = newCorrelationId();
        log.warn("[{}] Missing request parameter: {}", correlationId, ex.getParameterName());
        return ResponseEntity.badRequest()
                .body(ErrorResponse.of("ERR_MISSING_PARAMETER",
                        "A required request parameter is missing.", correlationId));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ErrorResponse> handleIllegalArgument(IllegalArgumentException ex) {
        String correlationId = newCorrelationId();
        log.warn("[{}] Invalid request", correlationId, ex);
        return ResponseEntity.badRequest()
                .body(ErrorResponse.of("ERR_INVALID_REQUEST",
                        "The request could not be processed.", correlationId));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception ex) {
        String correlationId = newCorrelationId();
        log.error("[{}] Unexpected error", correlationId, ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ErrorResponse.of("ERR_INTERNAL",
                        "An unexpected error occurred. Please try again later.", correlationId));
    }

    private String newCorrelationId() {
        return UUID.randomUUID().toString();
    }
}
