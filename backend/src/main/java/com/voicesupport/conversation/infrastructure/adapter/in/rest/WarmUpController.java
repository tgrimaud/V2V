package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.WarmUpResult;
import com.voicesupport.conversation.domain.port.in.WarmUpUseCase;
import com.voicesupport.shared.observability.CorrelationId;
import com.voicesupport.shared.web.rest.ErrorResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Connect-time warm-up surface (TASK-BE-017, ADR-0037): the voice runtime calls this once on WebRTC
// connect so the first real turn does not pay the cold embedding + LLM cost (lever 2 / TASK-WEB-021).
// Body-less; best-effort. It never invents or persists anything — the warmed answer is discarded and
// no conversation memory is touched. A warm-up miss returns 200 with the flags set to false so the
// runtime treats it as best-effort and still proceeds.
@RestController
@RequestMapping("/api/conversation")
@Tag(name = "Conversation")
public class WarmUpController {

    private static final Logger log = LoggerFactory.getLogger(WarmUpController.class);

    private final WarmUpUseCase warmUpUseCase;

    public WarmUpController(WarmUpUseCase warmUpUseCase) {
        this.warmUpUseCase = warmUpUseCase;
    }

    @PostMapping("/warm-up")
    @Operation(summary = "Warm up the answer models",
            description = "Exercises the embedding and LLM once so the first real turn is warm. "
                    + "Side-effect-free (no conversation memory, discarded output) and safe to call "
                    + "repeatedly. Always returns 200; a warm-up miss sets the flags to false.")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Warm-up outcome (per-model flags + duration)."),
            @ApiResponse(responseCode = "401", description = "Missing/invalid x-api-key when a shared secret is set.",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    public ResponseEntity<WarmUpResponse> warmUp() {
        WarmUpResult result = warmUpUseCase.warmUp();
        log.info("[WARMUP] embedding_warmed={} llm_warmed={} stream_warmed={} duration_ms={} correlation_id={}",
                result.embeddingWarmed(), result.llmWarmed(), result.streamWarmed(),
                result.durationMs(), CorrelationId.current());
        return ResponseEntity.ok(WarmUpResponse.from(result));
    }
}
