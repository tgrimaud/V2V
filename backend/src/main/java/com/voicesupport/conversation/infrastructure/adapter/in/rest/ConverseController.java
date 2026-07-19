package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
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
public class ConverseController {

    private static final Logger log = LoggerFactory.getLogger(ConverseController.class);
    private static final String LISTEN_PROMPT = "Je vous écoute, posez-moi votre question.";

    private final ConverseUseCase converseUseCase;
    private final String apiKey;

    public ConverseController(
            ConverseUseCase converseUseCase,
            @Value("${voice-support.conversation.api-key:}") String apiKey) {
        this.converseUseCase = converseUseCase;
        this.apiKey = apiKey;
    }

    @PostMapping("/converse")
    public ResponseEntity<ConverseResponse> converse(
            @RequestBody ConverseRequest request,
            @RequestHeader(value = "x-api-key", required = false) String providedKey) {
        if (!authorized(providedKey)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        if (!request.hasTranscript()) {
            return ResponseEntity.ok(ConverseResponse.of(LISTEN_PROMPT));
        }
        long start = System.nanoTime();
        // A missing/blank conversation id is treated as stateless (no shared memory bucket):
        // the memory adapter returns empty history and skips persistence, so callers that omit
        // the id can never see each other's turns.
        GeneratedAnswer answer = converseUseCase.converse(request.transcript(), request.conversationId());
        logTurn(request, answer, elapsedMs(start));
        return ResponseEntity.ok(ConverseResponse.from(answer));
    }

    private boolean authorized(String providedKey) {
        return apiKey == null || apiKey.isBlank() || apiKey.equals(providedKey);
    }

    private void logTurn(ConverseRequest request, GeneratedAnswer answer, long durationMs) {
        log.info("[CONVERSE] channel={} conversation_id={} correlation_id={} grounded={} confidence={} "
                        + "chars={} duration_ms={}",
                nullSafe(request.channel()), nullSafe(request.conversationId()), nullSafe(request.correlationId()),
                answer.grounded(), formatConfidence(answer.confidence()),
                answer.text() != null ? answer.text().length() : 0, durationMs);
    }

    private String nullSafe(String value) {
        return value == null || value.isBlank() ? "n/a" : value;
    }

    private String formatConfidence(Double confidence) {
        return confidence == null ? "n/a" : String.format(Locale.ROOT, "%.4f", confidence);
    }

    private static long elapsedMs(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }
}
