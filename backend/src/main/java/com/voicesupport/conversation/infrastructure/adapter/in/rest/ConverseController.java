package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.CorrelationId;
import com.voicesupport.shared.observability.Slices;
import com.voicesupport.shared.web.rest.ErrorResponse;
import com.voicesupport.shared.web.security.ApiKeyGuard;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Locale;

// ADR-0021 conversation endpoint the voice runtime calls (HttpBackendAdapter). Wires the
// full pipeline (input guardrail -> retrieval -> LLM wording -> output guardrail) with short
// conversation memory keyed by conversation_id. Always returns a safe, contract-shaped
// {text, confidence?}; the runtime maps failures to a spoken degraded turn on its side.
@RestController
@RequestMapping("/api/conversation")
@Tag(name = "Conversation")
public class ConverseController {

    private static final Logger log = LoggerFactory.getLogger(ConverseController.class);
    private static final String LISTEN_PROMPT = "Je vous écoute, posez-moi votre question.";

    private final ConverseUseCase converseUseCase;
    private final BackendTelemetry telemetry;
    private final ApiKeyGuard apiKeyGuard;

    public ConverseController(
            ConverseUseCase converseUseCase,
            BackendTelemetry telemetry,
            @Value("${voice-support.conversation.api-key:}") String apiKey) {
        this.converseUseCase = converseUseCase;
        this.telemetry = telemetry;
        this.apiKeyGuard = new ApiKeyGuard(apiKey);
    }

    @PostMapping("/converse")
    @Operation(summary = "Converse (voice-runtime contract)",
            description = "Full guarded pipeline (input guardrail, retrieval, LLM wording, output guardrail) "
                    + "with short conversation memory keyed by conversation_id. Always returns a safe "
                    + "{text, confidence?}; a blank transcript returns a listen prompt.")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "A safe, contract-shaped answer or a listen prompt."),
            @ApiResponse(responseCode = "401", description = "Missing/invalid x-api-key when a shared secret is set "
                    + "(empty body).", content = @Content),
            @ApiResponse(responseCode = "503", description = "A required upstream is unavailable.",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    public ResponseEntity<ConverseResponse> converse(
            @RequestBody ConverseRequest request,
            @Parameter(description = "Optional shared secret; required only when the backend api-key is set.")
            @RequestHeader(value = "x-api-key", required = false) String providedKey,
            HttpServletResponse httpResponse) {
        if (!apiKeyGuard.authorized(providedKey)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        // Align backend logs/metrics with the runtime's correlation id (authoritative, from the
        // body) and the originating channel, so this turn's slices share one id end to end, and
        // echo that id back (overwriting the filter's default) for runtime -> backend continuity.
        CorrelationId.set(request.correlationId());
        CorrelationId.setChannel(request.channel());
        httpResponse.setHeader(CorrelationId.HEADER, CorrelationId.current());
        if (!request.hasTranscript()) {
            return ResponseEntity.ok(ConverseResponse.of(LISTEN_PROMPT));
        }
        long start = System.nanoTime();
        // A missing/blank conversation id is treated as stateless (no shared memory bucket):
        // the memory adapter returns empty history and skips persistence, so callers that omit
        // the id can never see each other's turns.
        GeneratedAnswer answer = telemetry.time(Slices.BACKEND_REQUEST, "conversation",
                () -> converseUseCase.converse(request.transcript(), request.conversationId(), request.language()));
        logTurn(request, answer, elapsedMs(start));
        return ResponseEntity.ok(ConverseResponse.from(answer));
    }

    private void logTurn(ConverseRequest request, GeneratedAnswer answer, long durationMs) {
        log.info("[CONVERSE] channel={} conversation_id={} correlation_id={} grounded={} confidence={} "
                        + "chars={} duration_ms={}",
                nullSafe(request.channel()), nullSafe(request.conversationId()), nullSafe(request.correlationId()),
                answer.grounded(), formatConfidence(answer.confidence()),
                answer.text() != null ? answer.text().length() : 0, durationMs);
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

    private static long elapsedMs(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }
}
