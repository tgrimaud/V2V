package com.voicesupport.billing.domain.model;

import java.util.Objects;

// The deterministic result the billing context hands to the answer engine (TASK-BE-045, ADR-0051):
// the outcome, the grounded text (a fully-computed explanation the LLM may only rephrase — DEC-002 —
// or a safe operational/hand-off message), whether the turn must escalate fail-closed, the escalation
// code the conversation seam maps to an EscalationReason, and a provisional confidence. The billing
// context owns escalation as a stable code string so it never depends on the conversation context.
public record BillingExplanation(BillingExplanationOutcome outcome, String text, boolean escalate,
        String escalationCode, Double confidence, String reason) {

    public static final String CODE_IDENTITY_UNVERIFIED = "identity_unverified";
    public static final String CODE_BILLING_UNEXPLAINED = "billing_unexplained";

    // Stable, non-PII refinement of a NOT_ENOUGH_DATA escalation (TASK-BE-048), so Ops/QA can tell a
    // data gap from an evidence-fetch failure from a reconciliation gap. Never carries account/amount.
    public static final String REASON_INSUFFICIENT_HISTORY = "insufficient_history";
    public static final String REASON_EVIDENCE_UNFETCHABLE = "evidence_unfetchable";
    public static final String REASON_NO_USABLE_LINES = "no_usable_lines";
    public static final String REASON_RESIDUAL_TOO_HIGH = "residual_too_high";

    public BillingExplanation {
        Objects.requireNonNull(outcome, "outcome must not be null");
        Objects.requireNonNull(text, "text must not be null");
    }

    public static BillingExplanation explained(String text, double confidence) {
        return new BillingExplanation(BillingExplanationOutcome.EXPLAINED, text, false, null, confidence, null);
    }

    public static BillingExplanation partiallyExplained(String text, double confidence) {
        return new BillingExplanation(BillingExplanationOutcome.PARTIALLY_EXPLAINED, text, false, null, confidence, null);
    }

    public static BillingExplanation identityUnresolved(String text) {
        return new BillingExplanation(
                BillingExplanationOutcome.IDENTITY_UNRESOLVED, text, true, CODE_IDENTITY_UNVERIFIED, null, null);
    }

    public static BillingExplanation notEnoughData(String text) {
        return notEnoughData(text, null);
    }

    public static BillingExplanation notEnoughData(String text, String reason) {
        return new BillingExplanation(
                BillingExplanationOutcome.NOT_ENOUGH_DATA, text, true, CODE_BILLING_UNEXPLAINED, null, reason);
    }

    public static BillingExplanation notABillingRequest(String text) {
        return new BillingExplanation(BillingExplanationOutcome.NOT_A_BILLING_REQUEST, text, false, null, null, null);
    }

    // True when the text is a grounded explanation the LLM should rephrase; false when the text is a
    // safe operational/hand-off message to voice as-is (no LLM wording, no grounding claim).
    public boolean answerable() {
        return outcome == BillingExplanationOutcome.EXPLAINED
                || outcome == BillingExplanationOutcome.PARTIALLY_EXPLAINED;
    }
}
