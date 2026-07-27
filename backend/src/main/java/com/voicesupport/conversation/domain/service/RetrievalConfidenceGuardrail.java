package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.util.List;

// Post-retrieval guardrail (ADR-0014 / ADR-0034): three bands on the best evidence similarity.
// Below the floor -> low-confidence advisor hand-off (DEC-002: never answer on weak grounding).
// Between the floor and the clarify ceiling -> ask the customer to clarify rather than voice a
// weakly-matched (possibly wrong-audience) article (BUG-005). At or above the ceiling -> answer.
// The clarify band is inactive when clarifyThreshold <= confidenceThreshold (single-threshold ctor).
public class RetrievalConfidenceGuardrail {

    private static final double DEFAULT_CONFIDENCE_THRESHOLD = 0.5;

    private final double confidenceThreshold;
    private final double clarifyThreshold;

    public RetrievalConfidenceGuardrail() {
        this(DEFAULT_CONFIDENCE_THRESHOLD);
    }

    public RetrievalConfidenceGuardrail(double confidenceThreshold) {
        this(confidenceThreshold, confidenceThreshold);
    }

    public RetrievalConfidenceGuardrail(double confidenceThreshold, double clarifyThreshold) {
        this.confidenceThreshold = confidenceThreshold;
        this.clarifyThreshold = Math.max(clarifyThreshold, confidenceThreshold);
    }

    // The answer language is decided once per turn upstream (session stickiness + configurable
    // default) and passed in so the hand-off/clarify wording is spoken in the turn's language.
    public GuardrailDecision check(List<RetrievedEvidence> evidence, AnswerLanguage language) {
        if (evidence == null || evidence.isEmpty()) {
            return GuardrailDecision.lowConfidence(GuardrailMessages.lowConfidence(language));
        }
        double bestScore = evidence.stream().mapToDouble(RetrievedEvidence::score).max().orElse(0.0);
        if (bestScore < confidenceThreshold) {
            return GuardrailDecision.lowConfidence(GuardrailMessages.lowConfidence(language));
        }
        if (bestScore < clarifyThreshold) {
            return GuardrailDecision.clarify(GuardrailMessages.clarify(language));
        }
        return GuardrailDecision.pass();
    }
}
