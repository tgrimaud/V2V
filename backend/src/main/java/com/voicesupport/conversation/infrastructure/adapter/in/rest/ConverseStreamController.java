package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.CorrelationId;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;

// SSE streaming counterpart of ConverseController (ADR-0013 / TASK-BE-007): POST /converse-stream
// with the same ConverseRequest body. The servlet thread returns the SseEmitter immediately; a
// ConverseStreamSession runs the guarded pipeline on a bounded worker pool and pushes chunk/done/
// error events. The synchronous /converse endpoint stays the non-streaming fallback.
@RestController
@RequestMapping("/api/conversation")
public class ConverseStreamController {

    private static final long STREAM_TIMEOUT_MS = 60_000L;

    private final ConverseStreamUseCase converseStreamUseCase;
    private final BackendTelemetry telemetry;
    private final ExecutorService streamExecutor;
    private final String apiKey;

    public ConverseStreamController(
            ConverseStreamUseCase converseStreamUseCase,
            BackendTelemetry telemetry,
            ExecutorService sseStreamExecutor,
            @Value("${voice-support.conversation.api-key:}") String apiKey) {
        this.converseStreamUseCase = converseStreamUseCase;
        this.telemetry = telemetry;
        this.streamExecutor = sseStreamExecutor;
        this.apiKey = apiKey;
    }

    @PostMapping(value = "/converse-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<SseEmitter> converseStream(
            @RequestBody ConverseRequest request,
            @RequestHeader(value = "x-api-key", required = false) String providedKey,
            HttpServletResponse httpResponse) {
        if (!authorized(providedKey)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        // Resolve the authoritative correlation id on the request thread (body value wins over the
        // filter's default) and echo it back; the worker re-establishes it in its own MDC.
        String correlationId = resolveCorrelationId(request);
        httpResponse.setHeader(CorrelationId.HEADER, correlationId);
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT_MS);
        ConverseStreamSession session =
                new ConverseStreamSession(emitter, converseStreamUseCase, telemetry, request, correlationId);
        try {
            streamExecutor.execute(session::run);
        } catch (RejectedExecutionException e) {
            // Concurrent-stream ceiling reached: fail fast with a sanitized 503 instead of queueing.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }
        return ResponseEntity.ok(emitter);
    }

    private boolean authorized(String providedKey) {
        return apiKey == null || apiKey.isBlank() || apiKey.equals(providedKey);
    }

    private String resolveCorrelationId(ConverseRequest request) {
        String fromBody = request.correlationId();
        return fromBody != null && !fromBody.isBlank() ? fromBody : CorrelationId.current();
    }
}
