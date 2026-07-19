package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.in.AnswerQuestionUseCase;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.service.OutputGuardrail;

import java.util.List;

// Composes the LLM wording step (TASK-BE-005) on top of the BE-004 grounding pipeline:
// ground -> (if answerable) LLM wording -> output guardrail (DEC-002) -> answer. A blocked
// grounding decision or an ungrounded amount both yield a safe fallback, never an invented
// answer. Confidence reuses the provisional retrieval best-score policy (ADR-0021 / OQ-002).
// Conversation memory is not wired here (TASK-BE-006), so no history is sent to the LLM.
public class AnswerService implements AnswerQuestionUseCase {

    private final GroundQueryUseCase groundQueryUseCase;
    private final AnswerGeneratorPort answerGenerator;
    private final OutputGuardrail outputGuardrail;

    public AnswerService(
            GroundQueryUseCase groundQueryUseCase,
            AnswerGeneratorPort answerGenerator,
            OutputGuardrail outputGuardrail) {
        this.groundQueryUseCase = groundQueryUseCase;
        this.answerGenerator = answerGenerator;
        this.outputGuardrail = outputGuardrail;
    }

    @Override
    public GeneratedAnswer answer(
            String question, String domain, int topK, boolean alreadyGreeted, List<String> history) {
        GroundingResult grounding = groundQueryUseCase.ground(question, domain, topK, alreadyGreeted);
        if (!grounding.answerable()) {
            return GeneratedAnswer.fallback(grounding.decision().fallbackMessage());
        }
        List<RetrievedEvidence> evidence = grounding.evidence();
        String text = answerGenerator.generate(question, evidence, history == null ? List.of() : history);
        GuardrailDecision outputDecision = outputGuardrail.check(question, text, evidence);
        if (outputDecision.blocked()) {
            return GeneratedAnswer.fallback(outputDecision.fallbackMessage());
        }
        return GeneratedAnswer.grounded(text, bestScore(evidence));
    }

    private double bestScore(List<RetrievedEvidence> evidence) {
        return evidence.stream().mapToDouble(RetrievedEvidence::score).max().orElse(0.0);
    }
}
