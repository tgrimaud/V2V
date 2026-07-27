package com.voicesupport.conversation.domain.model.valueobject;

public record GuardrailDecision(Verdict verdict, String fallbackMessage) {

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
        return new GuardrailDecision(Verdict.PASS, null);
    }

    public static GuardrailDecision greeting(String message) {
        return new GuardrailDecision(Verdict.GREETING, message);
    }

    public static GuardrailDecision offTopic(String message) {
        return new GuardrailDecision(Verdict.OFF_TOPIC, message);
    }

    public static GuardrailDecision inappropriate(String message) {
        return new GuardrailDecision(Verdict.INAPPROPRIATE, message);
    }

    public static GuardrailDecision clarify(String message) {
        return new GuardrailDecision(Verdict.CLARIFY, message);
    }

    public static GuardrailDecision lowConfidence(String message) {
        return new GuardrailDecision(Verdict.LOW_CONFIDENCE, message);
    }

    public static GuardrailDecision ungrounded(String message) {
        return new GuardrailDecision(Verdict.UNGROUNDED, message);
    }
}
