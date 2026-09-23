package com.voicesupport.conversation.domain.model.valueobject;

// The `reason` is an optional low-cardinality sub-type tag for observability (ADR-0034): it lets
// telemetry distinguish otherwise-identical verdicts (e.g. a BUG-025 problem-opener CLARIFY from a
// vague/mid-confidence CLARIFY) without changing the verdict contract. Null when not applicable.
public record GuardrailDecision(Verdict verdict, String fallbackMessage, String reason) {

    public enum Verdict {
        PASS,
        GREETING,
        OFF_TOPIC,
        INAPPROPRIATE,
        // ADR-0034: a vague/low-information turn or a middle-confidence retrieval; the bot asks the
        // customer to clarify rather than voicing a weakly-matched (possibly wrong-audience) article.
        CLARIFY,
        LOW_CONFIDENCE,
        UNGROUNDED
    }

    public boolean blocked() {
        return verdict != Verdict.PASS;
    }

    public static GuardrailDecision pass() {
        return new GuardrailDecision(Verdict.PASS, null, null);
    }

    public static GuardrailDecision greeting(String message) {
        return new GuardrailDecision(Verdict.GREETING, message, null);
    }

    public static GuardrailDecision offTopic(String message) {
        return new GuardrailDecision(Verdict.OFF_TOPIC, message, null);
    }

    public static GuardrailDecision inappropriate(String message) {
        return new GuardrailDecision(Verdict.INAPPROPRIATE, message, null);
    }

    public static GuardrailDecision clarify(String message) {
        return new GuardrailDecision(Verdict.CLARIFY, message, null);
    }

    // BUG-025: a CLARIFY carrying a sub-type reason (e.g. "problem_opener") so the redirect is
    // measurable in telemetry separately from the generic vague/mid-confidence clarify.
    public static GuardrailDecision clarify(String message, String reason) {
        return new GuardrailDecision(Verdict.CLARIFY, message, reason);
    }

    public static GuardrailDecision lowConfidence(String message) {
        return new GuardrailDecision(Verdict.LOW_CONFIDENCE, message, null);
    }

    public static GuardrailDecision ungrounded(String message) {
        return new GuardrailDecision(Verdict.UNGROUNDED, message, null);
    }
}
