package com.voicesupport.conversation.domain.model.valueobject;

// Result of the LLM wording step (TASK-BE-005): the spoken answer text plus a provisional
// confidence signal (ADR-0021 / OQ-002 policy). `grounded` is false when the text comes
// from a guardrail fallback (blocked input, low confidence, or an ungrounded amount caught
// by the output guardrail per DEC-002) rather than from a grounded LLM answer. `escalation`
// is non-null only when that fallback is an ADR-0019 escalation trigger (low confidence /
// ungrounded billing amount), so the escalation path can emit a by-reference hand-off
// (TASK-BE-036 / DEC-013) without any channel-specific logic reaching the domain.
public record GeneratedAnswer(String text, Double confidence, boolean grounded, EscalationReason escalation) {

    public static GeneratedAnswer grounded(String text, double confidence) {
        return new GeneratedAnswer(text, confidence, true, null);
    }

    public static GeneratedAnswer fallback(String text) {
        return new GeneratedAnswer(text, null, false, null);
    }

    // Fallback choke point that also records the escalation reason a blocked verdict maps to
    // (empty for non-escalating verdicts), so the spoken wording is unchanged (ADR-0019) while the
    // machine-to-machine hand-off can travel by reference. Keeps escalation detection in the domain.
    public static GeneratedAnswer fallback(String text, GuardrailDecision.Verdict verdict) {
        return new GeneratedAnswer(text, null, false, EscalationReason.fromVerdict(verdict).orElse(null));
    }

    public boolean requiresEscalation() {
        return escalation != null;
    }
}
