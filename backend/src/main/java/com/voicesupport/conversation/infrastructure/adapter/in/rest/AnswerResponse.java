package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;

// Wording-step contract (TASK-BE-005): the spoken text plus a provisional confidence signal
// (null when the answer is a guardrail fallback). The definitive ADR-0021 voice-runtime
// contract ({text, confidence} over the exact field names + memory) lands with TASK-BE-006.
public record AnswerResponse(String text, Double confidence, boolean grounded) {

    public static AnswerResponse from(GeneratedAnswer answer) {
        return new AnswerResponse(answer.text(), answer.confidence(), answer.grounded());
    }
}
