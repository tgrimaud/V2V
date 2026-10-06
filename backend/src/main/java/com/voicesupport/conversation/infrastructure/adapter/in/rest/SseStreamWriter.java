package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.CorrelationId;
import com.voicesupport.shared.web.rest.ErrorResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;

// Wraps the per-turn SseEmitter: serializes each event as JSON, maps a broken pipe to
// SseSendException so the session can report a client disconnect, and emits the sanitized terminal
// error contract (the @RestControllerAdvice does not apply to async worker exceptions, so it is
// mirrored here). Extracted from ConverseStreamSession for the 200-line budget; behaviour unchanged.
class SseStreamWriter {

    private static final Logger log = LoggerFactory.getLogger(SseStreamWriter.class);
    private static final String ERR_UPSTREAM = "ERR_UPSTREAM";
    private static final String ERR_INTERNAL = "ERR_INTERNAL";
    private static final String MSG_UPSTREAM = "A required service is temporarily unavailable. Please retry shortly.";
    private static final String MSG_INTERNAL = "An unexpected error occurred.";

    private final SseEmitter emitter;

    SseStreamWriter(SseEmitter emitter) {
        this.emitter = emitter;
    }

    void send(String event, Object payload) {
        try {
            emitter.send(SseEmitter.event().name(event).data(payload, MediaType.APPLICATION_JSON));
        } catch (IOException | IllegalStateException e) {
            throw new SseSendException(e);
        }
    }

    void complete() {
        emitter.complete();
    }

    void abort(Throwable cause) {
        emitter.completeWithError(cause);
    }

    void completeExceptionally(RuntimeException e) {
        boolean upstream = e instanceof UpstreamUnavailableException;
        String code = upstream ? ERR_UPSTREAM : ERR_INTERNAL;
        String message = upstream ? MSG_UPSTREAM : MSG_INTERNAL;
        log.error("[CONVERSE-STREAM] code={} correlation_id={} type={}",
                code, CorrelationId.current(), e.getClass().getSimpleName(), e);
        try {
            emitter.send(SseEmitter.event().name("error")
                    .data(ErrorResponse.of(code, message, CorrelationId.current()), MediaType.APPLICATION_JSON));
            emitter.complete();
        } catch (IOException | IllegalStateException ignored) {
            emitter.completeWithError(e);
        }
    }

    static final class SseSendException extends RuntimeException {
        SseSendException(Throwable cause) {
            super(cause);
        }
    }
}
