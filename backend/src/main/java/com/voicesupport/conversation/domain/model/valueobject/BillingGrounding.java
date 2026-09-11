package com.voicesupport.conversation.domain.model.valueobject;

// The billing context's deterministic result as the answer engine consumes it (TASK-BE-045,
// ADR-0051): the grounded text (an explanation the LLM may only rephrase — DEC-002 — or a safe
// operational/hand-off message), whether it is answerable (rephrase via LLM) or must be voiced
// as-is, whether the turn escalates fail-closed, the escalation reason (non-null only when
// escalate is true), and a provisional confidence. Conversation-owned; the outbound seam maps the
// billing outcome onto it so the answer engine never references billing types.
public record BillingGrounding(String text, boolean answerable, boolean escalate,
        EscalationReason escalationReason, Double confidence) {

    public static BillingGrounding answerable(String text, Double confidence) {
        return new BillingGrounding(text, true, false, null, confidence);
    }

    public static BillingGrounding escalate(String text, EscalationReason reason) {
        return new BillingGrounding(text, false, true, reason, null);
    }

    public static BillingGrounding message(String text) {
        return new BillingGrounding(text, false, false, null, null);
    }
}
