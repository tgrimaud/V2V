package com.voicesupport.infrastructure.adapter.in.rest;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.MissingServletRequestParameterException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class GlobalExceptionHandlerTest {

    @Test
    void handle_missing_param_returns_generic_bad_request() {
        // GIVEN
        GlobalExceptionHandler handler = new GlobalExceptionHandler();

        // WHEN
        var response = handler.handleMissingParam(
                new MissingServletRequestParameterException("question", "String"));

        // THEN
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        assertEquals("ERR_MISSING_PARAMETER", response.getBody().code());
        assertNotNull(response.getBody().correlationId());
    }

    @Test
    void handle_illegal_argument_does_not_echo_exception_message() {
        // GIVEN
        GlobalExceptionHandler handler = new GlobalExceptionHandler();

        // WHEN
        var response = handler.handleIllegalArgument(new IllegalArgumentException("secret detail"));

        // THEN
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        assertEquals("ERR_INVALID_REQUEST", response.getBody().code());
        assertEquals("The request could not be processed.", response.getBody().message());
    }

    @Test
    void handle_unexpected_returns_generic_internal_error() {
        // GIVEN
        GlobalExceptionHandler handler = new GlobalExceptionHandler();

        // WHEN
        var response = handler.handleUnexpected(new RuntimeException("database detail"));

        // THEN
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, response.getStatusCode());
        assertEquals("ERR_INTERNAL", response.getBody().code());
        assertNotNull(response.getBody().correlationId());
    }
}
