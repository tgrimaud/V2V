package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.shared.web.rest.ErrorResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Locale;

// Retrieval + guardrails validation surface (TASK-BE-004). Runs the pre-LLM grounding
// pipeline and returns the guardrail decision plus grounded evidence. The full
// conversation/answer endpoint (memory + LLM wording + streaming) is TASK-BE-006.
@RestController
@RequestMapping("/api/conversation")
@Tag(name = "Conversation")
public class RetrievalController {

    private static final Logger log = LoggerFactory.getLogger(RetrievalController.class);

    private final GroundQueryUseCase groundQueryUseCase;
    private final LanguageDetector languageDetector;

    public RetrievalController(GroundQueryUseCase groundQueryUseCase, LanguageDetector languageDetector) {
        this.groundQueryUseCase = groundQueryUseCase;
        this.languageDetector = languageDetector;
    }

    @PostMapping("/retrieve")
    @Operation(summary = "Ground a query (pre-LLM)",
            description = "Runs retrieval and the grounding guardrail, returning the answerable verdict, an "
                    + "optional fallback message and the grounded evidence (no LLM wording).")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Grounding decision and evidence."),
            @ApiResponse(responseCode = "400", description = "Invalid request (e.g. blank question).",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "503", description = "A required upstream (vector store) is unavailable.",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    public ResponseEntity<RetrievalResponse> retrieve(@Valid @RequestBody RetrievalRequest request) {
        long start = System.nanoTime();
        // This validation surface has no conversation history, so the language is decided from the
        // question alone falling back to the configurable default (LanguageDetector, TASK-BE-015).
        AnswerLanguage language = languageDetector.resolve(request.question(), List.of());
        GroundingResult result = groundQueryUseCase.ground(
                request.question(), request.domain(), request.effectiveTopK(),
                request.effectiveAlreadyGreeted(), language);
        logDecision(request, result, elapsedMs(start));
        return ResponseEntity.ok(RetrievalResponse.from(result));
    }

    private void logDecision(RetrievalRequest request, GroundingResult result, long durationMs) {
        List<RetrievedEvidence> evidence = result.evidence();
        double bestScore = evidence.stream().mapToDouble(RetrievedEvidence::score).max().orElse(0.0);
        log.info("[GROUNDING] domain={} top_k={} answerable={} verdict={} hits={} best_score={} duration_ms={}",
                request.domain() != null ? request.domain() : "any", request.effectiveTopK(),
                result.answerable(), result.decision().verdict(), evidence.size(),
                String.format(Locale.ROOT, "%.4f", bestScore), durationMs);
    }

    private static long elapsedMs(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }
}
