package com.voicesupport.conversation.domain.model.valueobject;

// The by-reference hand-off token that is the ONLY thing allowed to cross the channel boundary
// (TASK-BE-036 / DEC-013): an opaque handoff_id plus the minimal, non-PII routing metadata the
// trust model permits (reason_code, priority) so Genesys can route without holding the audited
// context. The full EscalationHandoff (conversation context, PII) stays backend-owned and is
// fetched by handoff_id. Carrying the payload inline is rejected on PII/trust-boundary grounds, so
// this object deliberately exposes no summary, last user message or customer reference.
public record EscalationHandoffReference(String handoffId, String reasonCode, String priority) {

    public static EscalationHandoffReference of(HandoffId handoffId, EscalationReason reason) {
        return new EscalationHandoffReference(handoffId.value(), reason.code(), reason.priority());
    }
}
