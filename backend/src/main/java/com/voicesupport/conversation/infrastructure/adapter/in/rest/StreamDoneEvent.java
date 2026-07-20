package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;

// Terminal SSE `done` event payload (ADR-0013): the full voiced answer plus the confidence signal
// (omitted when absent) and whether it was a grounded answer or a guardrail fallback.
public record StreamDoneEvent(String text, Double confidence, boolean grounded) {

    public static StreamDoneEvent from(GeneratedAnswer answer) {
        return new StreamDoneEvent(answer.text(), answer.confidence(), answer.grounded());
    }
}
