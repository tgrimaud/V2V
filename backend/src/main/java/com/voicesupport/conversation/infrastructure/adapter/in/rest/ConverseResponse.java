package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import io.swagger.v3.oas.annotations.media.Schema;

// ADR-0021 response: the text to speak plus an optional confidence signal (omitted when
// absent). The voice runtime maps a 2xx text onto its neutral AnswerResult; a guardrail
// fallback is still a valid 2xx text so the runtime never needs raw provider text.
@Schema(description = "Answer to speak plus an optional confidence signal.")
public record ConverseResponse(
        @Schema(description = "Text to speak (may be a safe guardrail fallback).") String text,
        @Schema(description = "Confidence in [0,1]; omitted when absent.", example = "0.82") Double confidence) {

    public static ConverseResponse from(GeneratedAnswer answer) {
        return new ConverseResponse(answer.text(), answer.confidence());
    }

    public static ConverseResponse of(String text) {
        return new ConverseResponse(text, null);
    }
}
