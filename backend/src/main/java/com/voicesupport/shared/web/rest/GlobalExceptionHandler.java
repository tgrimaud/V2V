package com.voicesupport.shared.web.rest;

import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.CorrelationId;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClientException;

// Shared, sanitized REST error contract for both bounded contexts (TASK-BE-012). Client bodies
// carry only a stable error_code, a generic message and the correlation_id (TASK-BE-009); the
// full exception detail is logged server-side under the same id. Never echoes ex.getMessage()
// to the client (no upstream URLs, driver text or stack hints).
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    private static final String ERR_400 = "ERR_400";
    private static final String ERR_UPSTREAM = "ERR_UPSTREAM";
    private static final String ERR_INTERNAL = "ERR_INTERNAL";
    private static final String MSG_400 = "The request is invalid.";
    private static final String MSG_UPSTREAM = "A required service is temporarily unavailable. Please retry shortly.";
    private static final String MSG_INTERNAL = "An unexpected error occurred.";

    @ExceptionHandler({MethodArgumentNotValidException.class, HttpMessageNotReadableException.class})
    public ResponseEntity<ErrorResponse> handleBadRequest(Exception ex) {
        log.warn("[ERROR] code={} correlation_id={} type={} reason={}",
                ERR_400, CorrelationId.current(), ex.getClass().getSimpleName(), ex.getMessage());
        return build(HttpStatus.BAD_REQUEST, ERR_400, MSG_400);
    }

    // Dependency failures map to a sanitized 503: our own UpstreamUnavailableException (e.g. LLM
    // timeout), a vector-store failure (DataAccessException), and any REST client failure raised
    // by an embedding/LLM provider adapter on the retrieval path (RestClientException, incl.
    // ResourceAccessException for connection refused/read timeouts).
    @ExceptionHandler({UpstreamUnavailableException.class, DataAccessException.class, RestClientException.class})
    public ResponseEntity<ErrorResponse> handleUpstream(Exception ex) {
        // Full detail (cause, message) server-side only; the client never sees the upstream text.
        log.error("[ERROR] code={} correlation_id={} type={}",
                ERR_UPSTREAM, CorrelationId.current(), ex.getClass().getSimpleName(), ex);
        return build(HttpStatus.SERVICE_UNAVAILABLE, ERR_UPSTREAM, MSG_UPSTREAM);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception ex) {
        log.error("[ERROR] code={} correlation_id={} type={}",
                ERR_INTERNAL, CorrelationId.current(), ex.getClass().getSimpleName(), ex);
        return build(HttpStatus.INTERNAL_SERVER_ERROR, ERR_INTERNAL, MSG_INTERNAL);
    }

    private ResponseEntity<ErrorResponse> build(HttpStatus status, String code, String message) {
        return ResponseEntity.status(status).body(ErrorResponse.of(code, message, CorrelationId.current()));
    }
}
