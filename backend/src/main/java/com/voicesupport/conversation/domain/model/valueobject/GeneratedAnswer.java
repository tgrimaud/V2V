package com.voicesupport.conversation.domain.model.valueobject;

// Result of the LLM wording step (TASK-BE-005): the spoken answer text plus a provisional
// confidence signal (ADR-0021 / OQ-002 policy). `grounded` is false when the text comes
// from a guardrail fallback (blocked input, low confidence, or an ungrounded amount caught
// by the output guardrail per DEC-002) rather than from a grounded LLM answer.
public record GeneratedAnswer(String text, Double confidence, boolean grounded) {

    public static GeneratedAnswer grounded(String text, double confidence) {
        return new GeneratedAnswer(text, confidence, true);
    }

    public static GeneratedAnswer fallback(String text) {
        return new GeneratedAnswer(text, null, false);
    }
}
