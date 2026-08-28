package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import io.swagger.v3.oas.annotations.media.Schema;

// ADR-0021 response: the text to speak plus an optional confidence signal (omitted when
// absent). The voice runtime maps a 2xx text onto its neutral AnswerResult; a guardrail
// fallback is still a valid 2xx text so the runtime never needs raw provider text. On an
// escalation turn (TASK-BE-036 / DEC-013) an `escalation_context` carries ONLY the by-reference
// hand-off token (handoff_id + non-PII routing metadata) — never the inline audited payload;
// it is omitted (NON_NULL) on ordinary turns so the existing contract is unchanged.
@Schema(description = "Answer to speak plus an optional confidence signal and escalation reference.")
public record ConverseResponse(
        @Schema(description = "Text to speak (may be a safe guardrail fallback).") String text,
        @Schema(description = "Confidence in [0,1]; omitted when absent.", example = "0.82") Double confidence,
        @Schema(description = "By-reference hand-off token; present only on an escalation turn.")
        EscalationHandoffReference escalationContext) {

    public static ConverseResponse from(GeneratedAnswer answer, EscalationHandoffReference escalationContext) {
        return new ConverseResponse(answer.text(), answer.confidence(), escalationContext);
    }

    public static ConverseResponse of(String text) {
        return new ConverseResponse(text, null, null);
    }
}
