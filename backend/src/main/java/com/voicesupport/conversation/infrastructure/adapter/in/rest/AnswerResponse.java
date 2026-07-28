package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import io.swagger.v3.oas.annotations.media.Schema;

// Wording-step contract (TASK-BE-005): the spoken text plus a provisional confidence signal
// (null when the answer is a guardrail fallback). The definitive ADR-0021 voice-runtime
// contract ({text, confidence} over the exact field names + memory) lands with TASK-BE-006.
@Schema(description = "Wording-step answer with grounding signal.")
public record AnswerResponse(
        @Schema(description = "Answer text (may be a safe guardrail fallback).") String text,
        @Schema(description = "Confidence in [0,1]; omitted when absent.", example = "0.82") Double confidence,
        @Schema(description = "True when the answer is grounded on retrieved evidence.") boolean grounded) {

    public static AnswerResponse from(GeneratedAnswer answer) {
        return new AnswerResponse(answer.text(), answer.confidence(), answer.grounded());
    }
}
