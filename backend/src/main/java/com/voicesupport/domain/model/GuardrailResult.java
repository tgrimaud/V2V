package com.voicesupport.domain.model;

public record GuardrailResult(Verdict verdict, String fallbackMessage) {

    public enum Verdict {
        PASS,
        OFF_TOPIC,
        LOW_CONFIDENCE
    }

    public boolean blocked() {
        return verdict != Verdict.PASS;
    }

    public static GuardrailResult pass() {
        return new GuardrailResult(Verdict.PASS, null);
    }

    public static GuardrailResult offTopic(String message) {
        return new GuardrailResult(Verdict.OFF_TOPIC, message);
    }

    public static GuardrailResult lowConfidence(String message) {
        return new GuardrailResult(Verdict.LOW_CONFIDENCE, message);
    }
}
