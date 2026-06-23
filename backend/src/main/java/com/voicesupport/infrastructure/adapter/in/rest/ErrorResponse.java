package com.voicesupport.infrastructure.adapter.in.rest;

import com.fasterxml.jackson.annotation.JsonProperty;

public record ErrorResponse(
        String code,
        String message,
        @JsonProperty("correlation_id") String correlationId) {

    public static ErrorResponse of(String code, String message, String correlationId) {
        return new ErrorResponse(code, message, correlationId);
    }
}
