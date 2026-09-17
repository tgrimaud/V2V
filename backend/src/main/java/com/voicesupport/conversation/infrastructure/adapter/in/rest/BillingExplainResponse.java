package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import io.swagger.v3.oas.annotations.media.Schema;

// Billing-explanation response (TASK-BE-045, ADR-0051): the text to speak plus an optional confidence
// signal, and — only on an escalation turn — the by-reference hand-off token (ADR-0019 / DEC-013).
// The escalation_context carries ONLY the handoff_id + non-PII routing metadata; the audited context
// (customer reference, summary) stays backend-owned. Same shape family as ConverseResponse.
@Schema(description = "Billing answer to speak plus an optional confidence signal and escalation reference.")
public record BillingExplainResponse(
        @Schema(description = "Text to speak (grounded explanation or safe hand-off).") String text,
        @Schema(description = "Confidence in [0,1]; omitted when absent.", example = "0.9") Double confidence,
        @Schema(description = "By-reference hand-off token; present only on an escalation turn.")
        EscalationHandoffReference escalationContext) {

    public static BillingExplainResponse from(GeneratedAnswer answer, EscalationHandoffReference escalationContext) {
        return new BillingExplainResponse(answer.text(), answer.confidence(), escalationContext);
    }
}
