package com.voicesupport.conversation.domain.model.valueobject;

import java.util.List;

// Outcome of the pre-LLM grounding pipeline: either answerable (guardrails passed,
// evidence attached) or blocked (a guardrail returned a canned fallback and no
// retrieval/LLM work should follow).
public record GroundingResult(GuardrailDecision decision, List<RetrievedEvidence> evidence) {

    public GroundingResult {
        evidence = evidence == null ? List.of() : List.copyOf(evidence);
    }

    public boolean answerable() {
        return !decision.blocked();
    }

    public static GroundingResult answerable(List<RetrievedEvidence> evidence) {
        return new GroundingResult(GuardrailDecision.pass(), evidence);
    }

    public static GroundingResult blocked(GuardrailDecision decision) {
        return new GroundingResult(decision, List.of());
    }
}
