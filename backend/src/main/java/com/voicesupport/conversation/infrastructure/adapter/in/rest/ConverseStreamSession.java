package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.ChannelEnvelope;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffCommand;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.port.in.PrepareEscalationHandoffUseCase;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
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
    private final IdempotentDeliveryGuard idempotentDeliveryGuard;
    private final PrepareEscalationHandoffUseCase prepareEscalationHandoffUseCase;
    private final BackendTelemetry telemetry;
    private final ConverseRequest request;
    private final ChannelEnvelope envelope;
    private final String correlationId;
    private final long startNanos = System.nanoTime();
    private boolean firstChunkSent;
    private boolean reserved;

    ConverseStreamSession(
            SseEmitter emitter,
            ConverseStreamUseCase converseStreamUseCase,
            IdempotentDeliveryGuard idempotentDeliveryGuard,
            PrepareEscalationHandoffUseCase prepareEscalationHandoffUseCase,
            BackendTelemetry telemetry,
            ConverseRequest request,
            String correlationId) {
        this.emitter = emitter;
        this.converseStreamUseCase = converseStreamUseCase;
        this.idempotentDeliveryGuard = idempotentDeliveryGuard;
        this.prepareEscalationHandoffUseCase = prepareEscalationHandoffUseCase;
        this.telemetry = telemetry;
        this.request = request;
        this.envelope = request.toEnvelope();
        this.correlationId = correlationId;
    }

    void run() {
        CorrelationId.set(correlationId);
        CorrelationId.setChannel(envelope.channel());
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
            releaseReservationIfUnfinished(outcome);
            telemetry.recordLatency(Slices.BACKEND_REQUEST, PROVIDER, outcome, elapsed());
            MDC.clear();
        }
    }

    private void stream() {
        if (!request.hasTranscript()) {
            emitListenPrompt();
            return;
        }
        // Duplicate protection on the primary voice path (streaming on by default): a re-delivered
        // turn is short-circuited to a safe listen prompt without reprocessing (TASK-BE-037 review #1).
        if (idempotentDeliveryGuard.isDuplicate(envelope)) {
            telemetry.recordChannelDelivery(envelope.replyMode().code(), true);
            emitListenPrompt();
            return;
        }
        processTurn();
    }

    private void processTurn() {
        reserved = true;
        telemetry.recordChannelDelivery(envelope.replyMode().code(), false);
        // Memory keys on the envelope's conversation key (external_session_id, falling back to
        // conversation_id) so a Genesys streaming call stays one coherent conversation.
        TokenStream tokenStream = converseStreamUseCase.converseStream(
                request.transcript(), envelope.conversationKey(), request.language());
        GeneratedAnswer answer = tokenStream.consume(this::onChunk);
        EscalationHandoffReference reference = prepareHandoffIfEscalated(answer);
        send("done", StreamDoneEvent.from(answer, reference));
        logTurn(answer);
    }

    // On an escalation turn, stores the audited hand-off and carries only the by-reference token on
    // the terminal `done` event, so the streamed voice path emits a handoff_id — never inline PII
    // (TASK-BE-036 / DEC-013). Ordinary turns return null and escalation_context is omitted.
    private EscalationHandoffReference prepareHandoffIfEscalated(GeneratedAnswer answer) {
        if (!answer.requiresEscalation()) {
            return null;
        }
        return prepareEscalationHandoffUseCase.prepare(
                EscalationHandoffCommand.of(envelope, request.transcript(), answer));
    }

    private void emitListenPrompt() {
        send("chunk", new StreamChunkEvent(LISTEN_PROMPT));
        send("done", StreamDoneEvent.from(GeneratedAnswer.fallback(LISTEN_PROMPT)));
    }

    // Confirms the idempotency reservation only when this turn completed successfully; a failed or
    // cancelled turn releases its own reserved key so a legitimate retry is reprocessed rather than
    // swallowed. Only releases a reservation this session actually made (TASK-BE-037 review #1/#3).
    private void releaseReservationIfUnfinished(String outcome) {
        if (reserved && !"success".equals(outcome)) {
            idempotentDeliveryGuard.releaseOnFailure(envelope);
        }
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
        log.info("[CONVERSE-STREAM] channel={} session_key={} correlation_id={} grounded={} confidence={} "
                        + "chars={} duration_ms={}",
                nullSafe(envelope.channel()), nullSafe(envelope.conversationKey()), nullSafe(request.correlationId()),
                answer.grounded(), formatConfidence(answer.confidence()),
                answer.text() != null ? answer.text().length() : 0, elapsed().toMillis());
    }

    private Duration elapsed() {
        return Duration.ofNanos(System.nanoTime() - startNanos);
    }

    // Sanitizes before logging: channel/conversation_id/correlation_id are client-controlled, so a
    // CR/LF-laced value could otherwise forge extra log lines (TASK-BE-022 review #3).
    private String nullSafe(String value) {
        String clean = CorrelationId.sanitize(value);
        return clean == null || clean.isBlank() ? "n/a" : clean;
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
