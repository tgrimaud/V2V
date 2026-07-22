package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.util.List;

// Post-retrieval guardrail (ADR-0014): when retrieved evidence is empty or its best
// similarity score is below the confidence threshold, block automation with a
// low-confidence fallback instead of letting the LLM answer on weak grounding (DEC-002).
public class RetrievalConfidenceGuardrail {

    private static final double DEFAULT_CONFIDENCE_THRESHOLD = 0.5;

    private final double confidenceThreshold;

    public RetrievalConfidenceGuardrail() {
        this(DEFAULT_CONFIDENCE_THRESHOLD);
    }

    public RetrievalConfidenceGuardrail(double confidenceThreshold) {
        this.confidenceThreshold = confidenceThreshold;
    }

    // The answer language is decided once per turn upstream (session stickiness + configurable
    // default) and passed in so the low-confidence hand-off is spoken in the turn's language.
    public GuardrailDecision check(List<RetrievedEvidence> evidence, AnswerLanguage language) {
        if (evidence == null || evidence.isEmpty()) {
            return GuardrailDecision.lowConfidence(GuardrailMessages.lowConfidence(language));
        }
        double bestScore = evidence.stream().mapToDouble(RetrievedEvidence::score).max().orElse(0.0);
        if (bestScore < confidenceThreshold) {
            return GuardrailDecision.lowConfidence(GuardrailMessages.lowConfidence(language));
        }
        return GuardrailDecision.pass();
    }
}
