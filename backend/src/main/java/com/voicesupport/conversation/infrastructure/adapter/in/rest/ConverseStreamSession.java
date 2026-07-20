package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.CorrelationId;
import com.voicesupport.shared.observability.Slices;
import com.voicesupport.shared.web.rest.ErrorResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Duration;
import java.util.Locale;

// Runs one /converse-stream turn on a worker thread (ADR-0013). It re-establishes the request
// correlation id + channel in this thread's MDC (thread-pool threads don't inherit it), consumes
// the guarded TokenStream, and pushes SSE events: `chunk` per safe sentence, one terminal `done`,
// or a sanitized `error` (the @RestControllerAdvice does not apply to async worker exceptions, so
// the contract is mirrored here). Records backend_first_token and backend_request slices.
class ConverseStreamSession {

    private static final Logger log = LoggerFactory.getLogger(ConverseStreamSession.class);
    private static final String PROVIDER = "conversation";
    private static final String LISTEN_PROMPT = "Je vous écoute, posez-moi votre question.";
    private static final String ERR_UPSTREAM = "ERR_UPSTREAM";
    private static final String ERR_INTERNAL = "ERR_INTERNAL";
    private static final String MSG_UPSTREAM = "A required service is temporarily unavailable. Please retry shortly.";
    private static final String MSG_INTERNAL = "An unexpected error occurred.";

    private final SseEmitter emitter;
    private final ConverseStreamUseCase converseStreamUseCase;
    private final BackendTelemetry telemetry;
    private final ConverseRequest request;
    private final String correlationId;
    private final long startNanos = System.nanoTime();
    private boolean firstChunkSent;

    ConverseStreamSession(
            SseEmitter emitter,
            ConverseStreamUseCase converseStreamUseCase,
            BackendTelemetry telemetry,
            ConverseRequest request,
            String correlationId) {
        this.emitter = emitter;
        this.converseStreamUseCase = converseStreamUseCase;
        this.telemetry = telemetry;
        this.request = request;
        this.correlationId = correlationId;
    }

    void run() {
        CorrelationId.set(correlationId);
        CorrelationId.setChannel(request.channel());
        String outcome = "success";
        try {
            stream();
            emitter.complete();
        } catch (SseSendException e) {
            outcome = "cancelled";
            log.info("[CONVERSE-STREAM] client_disconnected correlation_id={}", CorrelationId.current());
            emitter.completeWithError(e);
        } catch (RuntimeException e) {
            outcome = "error";
            completeWithError(e);
        } finally {
            telemetry.recordLatency(Slices.BACKEND_REQUEST, PROVIDER, outcome, elapsed());
            MDC.clear();
        }
    }

    private void stream() {
        if (!request.hasTranscript()) {
            send("chunk", new StreamChunkEvent(LISTEN_PROMPT));
            send("done", StreamDoneEvent.from(GeneratedAnswer.fallback(LISTEN_PROMPT)));
            return;
        }
        TokenStream tokenStream = converseStreamUseCase.converseStream(request.transcript(), request.conversationId());
        GeneratedAnswer answer = tokenStream.consume(this::onChunk);
        send("done", StreamDoneEvent.from(answer));
        logTurn(answer);
    }

    private void onChunk(String text) {
        if (!firstChunkSent) {
            firstChunkSent = true;
            telemetry.recordLatency(Slices.BACKEND_FIRST_TOKEN, PROVIDER, "success", elapsed());
        }
        send("chunk", new StreamChunkEvent(text));
    }

    private void send(String event, Object payload) {
        try {
            emitter.send(SseEmitter.event().name(event).data(payload, MediaType.APPLICATION_JSON));
        } catch (IOException | IllegalStateException e) {
            throw new SseSendException(e);
        }
    }

    private void completeWithError(RuntimeException e) {
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

    private void logTurn(GeneratedAnswer answer) {
        log.info("[CONVERSE-STREAM] channel={} conversation_id={} correlation_id={} grounded={} confidence={} "
                        + "chars={} duration_ms={}",
                nullSafe(request.channel()), nullSafe(request.conversationId()), nullSafe(request.correlationId()),
                answer.grounded(), formatConfidence(answer.confidence()),
                answer.text() != null ? answer.text().length() : 0, elapsed().toMillis());
    }

    private Duration elapsed() {
        return Duration.ofNanos(System.nanoTime() - startNanos);
    }

    private String nullSafe(String value) {
        return value == null || value.isBlank() ? "n/a" : value;
    }

    private String formatConfidence(Double confidence) {
        return confidence == null ? "n/a" : String.format(Locale.ROOT, "%.4f", confidence);
    }

    private static final class SseSendException extends RuntimeException {
        private SseSendException(Throwable cause) {
            super(cause);
        }
    }
}
