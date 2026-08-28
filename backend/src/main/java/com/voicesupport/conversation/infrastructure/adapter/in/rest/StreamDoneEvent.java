package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;

// Terminal SSE `done` event payload (ADR-0013): the full voiced answer plus the confidence signal
// (omitted when absent) and whether it was a grounded answer or a guardrail fallback. On an
// escalation turn (TASK-BE-036 / DEC-013) an `escalation_context` carries ONLY the by-reference
// hand-off token (handoff_id + non-PII routing metadata), omitted (NON_NULL) otherwise so the
// existing chunk/done contract is unchanged for ordinary turns.
public record StreamDoneEvent(
        String text, Double confidence, boolean grounded, EscalationHandoffReference escalationContext) {

    public static StreamDoneEvent from(GeneratedAnswer answer) {
        return new StreamDoneEvent(answer.text(), answer.confidence(), answer.grounded(), null);
    }

    public static StreamDoneEvent from(GeneratedAnswer answer, EscalationHandoffReference escalationContext) {
        return new StreamDoneEvent(answer.text(), answer.confidence(), answer.grounded(), escalationContext);
    }
}
