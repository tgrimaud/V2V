package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
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
public class RetrievalController {

    private static final Logger log = LoggerFactory.getLogger(RetrievalController.class);

    private final GroundQueryUseCase groundQueryUseCase;

    public RetrievalController(GroundQueryUseCase groundQueryUseCase) {
        this.groundQueryUseCase = groundQueryUseCase;
    }

    @PostMapping("/retrieve")
    public ResponseEntity<RetrievalResponse> retrieve(@Valid @RequestBody RetrievalRequest request) {
        long start = System.nanoTime();
        GroundingResult result = groundQueryUseCase.ground(
                request.question(), request.domain(), request.effectiveTopK(), request.effectiveAlreadyGreeted());
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
