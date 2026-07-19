package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;

// ADR-0021 response: the text to speak plus an optional confidence signal (omitted when
// absent). The voice runtime maps a 2xx text onto its neutral AnswerResult; a guardrail
// fallback is still a valid 2xx text so the runtime never needs raw provider text.
public record ConverseResponse(String text, Double confidence) {

    public static ConverseResponse from(GeneratedAnswer answer) {
        return new ConverseResponse(answer.text(), answer.confidence());
    }

    public static ConverseResponse of(String text) {
        return new ConverseResponse(text, null);
    }
}
