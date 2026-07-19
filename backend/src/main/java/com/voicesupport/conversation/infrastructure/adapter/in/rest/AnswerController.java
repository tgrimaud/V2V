package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.AnswerQuestionUseCase;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Locale;

// LLM wording validation surface (TASK-BE-005): grounding -> LLM wording -> output guardrail
// (DEC-002). The definitive ADR-0021 voice-runtime contract (exact field names, api-key,
// conversation memory, streaming) lands with TASK-BE-006.
@RestController
@RequestMapping("/api/conversation")
public class AnswerController {

    private static final Logger log = LoggerFactory.getLogger(AnswerController.class);

    private final AnswerQuestionUseCase answerQuestionUseCase;

    public AnswerController(AnswerQuestionUseCase answerQuestionUseCase) {
        this.answerQuestionUseCase = answerQuestionUseCase;
    }

    @PostMapping("/answer")
    public ResponseEntity<AnswerResponse> answer(@RequestBody AnswerRequest request) {
        long start = System.nanoTime();
        GeneratedAnswer answer = answerQuestionUseCase.answer(
                request.question(), request.domain(), request.effectiveTopK(), request.effectiveAlreadyGreeted());
        logAnswer(request, answer, elapsedMs(start));
        return ResponseEntity.ok(AnswerResponse.from(answer));
    }

    private void logAnswer(AnswerRequest request, GeneratedAnswer answer, long durationMs) {
        log.info("[ANSWER] domain={} top_k={} grounded={} confidence={} chars={} duration_ms={}",
                request.domain() != null ? request.domain() : "any", request.effectiveTopK(),
                answer.grounded(), formatConfidence(answer.confidence()),
                answer.text() != null ? answer.text().length() : 0, durationMs);
    }

    private String formatConfidence(Double confidence) {
        return confidence == null ? "n/a" : String.format(Locale.ROOT, "%.4f", confidence);
    }

    private static long elapsedMs(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }
}
