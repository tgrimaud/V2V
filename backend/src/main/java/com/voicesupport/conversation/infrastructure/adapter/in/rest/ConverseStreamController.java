package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.CorrelationId;
import com.voicesupport.shared.web.security.ApiKeyGuard;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
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
@Tag(name = "Conversation")
public class ConverseStreamController {

    private static final long STREAM_TIMEOUT_MS = 60_000L;

    private final ConverseStreamUseCase converseStreamUseCase;
    private final IdempotentDeliveryGuard idempotentDeliveryGuard;
    private final BackendTelemetry telemetry;
    private final ExecutorService streamExecutor;
    private final ApiKeyGuard apiKeyGuard;

    public ConverseStreamController(
            ConverseStreamUseCase converseStreamUseCase,
            IdempotentDeliveryGuard idempotentDeliveryGuard,
            BackendTelemetry telemetry,
            ExecutorService sseStreamExecutor,
            @Value("${voice-support.conversation.api-key:}") String apiKey) {
        this.converseStreamUseCase = converseStreamUseCase;
        this.idempotentDeliveryGuard = idempotentDeliveryGuard;
        this.telemetry = telemetry;
        this.streamExecutor = sseStreamExecutor;
        this.apiKeyGuard = new ApiKeyGuard(apiKey);
    }

    @PostMapping(value = "/converse-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @Operation(summary = "Converse with SSE streaming",
            description = "Same body as /converse but streams Server-Sent Events: `chunk` (partial text), "
                    + "`done` (final {text, confidence?, grounded}) and `error` (the ErrorResponse contract).")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "text/event-stream of chunk/done/error events."),
            @ApiResponse(responseCode = "401", description = "Missing/invalid x-api-key when a shared secret is set "
                    + "(empty body).", content = @Content),
            @ApiResponse(responseCode = "503", description = "Concurrent-stream ceiling reached (empty body).",
                    content = @Content)
    })
    public ResponseEntity<SseEmitter> converseStream(
            @RequestBody ConverseRequest request,
            @Parameter(description = "Optional shared secret; required only when the backend api-key is set.")
            @RequestHeader(value = "x-api-key", required = false) String providedKey,
            HttpServletResponse httpResponse) {
        if (!apiKeyGuard.authorized(providedKey)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        // Resolve the authoritative correlation id on the request thread (body value wins over the
        // filter's default) and echo it back; the worker re-establishes it in its own MDC.
        String correlationId = resolveCorrelationId(request);
        httpResponse.setHeader(CorrelationId.HEADER, correlationId);
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT_MS);
        ConverseStreamSession session = new ConverseStreamSession(
                emitter, converseStreamUseCase, idempotentDeliveryGuard, telemetry, request, correlationId);
        try {
            streamExecutor.execute(session::run);
        } catch (RejectedExecutionException e) {
            // Concurrent-stream ceiling reached: fail fast with a sanitized 503 instead of queueing.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }
        return ResponseEntity.ok(emitter);
    }

    private String resolveCorrelationId(ConverseRequest request) {
        // Sanitize the body-supplied id before it is echoed on the response header / re-established
        // in the worker MDC, closing CR/LF header-splitting + log injection (TASK-BE-022 review #3).
        String fromBody = CorrelationId.sanitize(request.correlationId());
        return fromBody != null && !fromBody.isBlank() ? fromBody : CorrelationId.current();
    }
}
