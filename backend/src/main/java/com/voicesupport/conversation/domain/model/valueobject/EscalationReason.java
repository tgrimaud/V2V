package com.voicesupport.conversation.domain.model.valueobject;

import java.util.Optional;

// The backend-owned escalation reason (ADR-0019 triggers) that a reactive guardrail block maps to.
// The backend decides escalation — never the channel (ADR-0019 / ADR-0009) — so this enum is the
// single source of the reason_code, reason_label, priority, evidence_status and recommended next
// action carried by an EscalationHandoff and its routing reference. Today only the two implemented
// reactive triggers are represented: low retrieval confidence and a blocked (ungrounded) billing
// amount; the enum extends as ADR-0019's other triggers become runtime signals.
public enum EscalationReason {

    LOW_CONFIDENCE(
            "low_confidence",
            "Low retrieval confidence",
            "normal",
            "insufficient_evidence",
            "Route to a support advisor to answer the customer's question."),
    BILLING_UNCERTAINTY(
            "billing_uncertainty",
            "Billing evidence uncertainty",
            "high",
            "unverified_amount",
            "Route to a billing advisor to review the customer's billing details.");

    private final String code;
    private final String label;
    private final String priority;
    private final String evidenceStatus;
    private final String recommendedNextAction;

    EscalationReason(String code, String label, String priority, String evidenceStatus,
            String recommendedNextAction) {
        this.code = code;
        this.label = label;
        this.priority = priority;
        this.evidenceStatus = evidenceStatus;
        this.recommendedNextAction = recommendedNextAction;
    }

    // Maps a blocked guardrail verdict to the escalation reason it represents; a non-escalating
    // verdict (greeting, clarify, off-topic, inappropriate, pass) yields empty so those turns stay
    // ordinary fallbacks and never produce a hand-off.
    public static Optional<EscalationReason> fromVerdict(GuardrailDecision.Verdict verdict) {
        // Deliberately if/else rather than an enum switch: a `switch` over the enum makes the compiler
        // synthesize a switch-map class in this value-object package, which the ArchUnit
        // "records or final" rule rejects.
        if (verdict == GuardrailDecision.Verdict.LOW_CONFIDENCE) {
            return Optional.of(LOW_CONFIDENCE);
        }
        if (verdict == GuardrailDecision.Verdict.UNGROUNDED) {
            return Optional.of(BILLING_UNCERTAINTY);
        }
        return Optional.empty();
    }

    public String code() {
        return code;
    }

    public String label() {
        return label;
    }

    public String priority() {
        return priority;
    }

    public String evidenceStatus() {
        return evidenceStatus;
    }

    public String recommendedNextAction() {
        return recommendedNextAction;
    }
}
