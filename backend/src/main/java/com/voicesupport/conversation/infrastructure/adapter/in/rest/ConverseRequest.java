package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.ChannelEnvelope;
import io.swagger.v3.oas.annotations.media.Schema;

// ADR-0021 conversation contract (matches the voice runtime's HttpBackendAdapter payload): the
// transcript to answer plus traceability ids and the normalized channel envelope (TASK-BE-037 /
// ADR-0009). Wire field names are snake_case via the global Jackson SNAKE_CASE strategy
// (JacksonConfig) — e.g. external_session_id, reply_mode. The envelope fields are optional, so
// existing web callers that omit them keep their exact behaviour.
@Schema(description = "Conversation turn: the transcript to answer plus traceability ids and the channel envelope.")
public record ConverseRequest(
        @Schema(description = "Customer utterance to answer. Blank returns a listen prompt.",
                example = "Pourquoi ma facture a augmenté ce mois-ci ?") String transcript,
        @Schema(description = "Conversation id for short memory. Blank/absent = stateless turn.",
                example = "conv-1234") String conversationId,
        @Schema(description = "Correlation id propagated across logs/metrics and echoed back.",
                example = "corr-abcd") String correlationId,
        @Schema(description = "Originating channel.", example = "web_voice") String channel,
        // US-042: optional UI-selected language ("fr"/"en"); when present it forces the answer
        // language, overriding backend auto-detection. Null/blank keeps detection behavior.
        @Schema(description = "Optional forced answer language (fr|en); blank keeps auto-detection.",
                example = "fr") String language,
        // TASK-BE-037 normalized channel envelope (ADR-0009): channel-identity + idempotency data a
        // channel adapter (e.g. Genesys) supplies so routing/escalation/memory stay consistent.
        @Schema(description = "Channel session id (e.g. Genesys conversationId); memory keys on it.",
                example = "genesys-conv-9") String externalSessionId,
        @Schema(description = "Last inbound event id for the turn (idempotency input).",
                example = "evt-42") String messageId,
        @Schema(description = "Idempotency key for safe retries / duplicate delivery.",
                example = "idem-42") String idempotencyKey,
        @Schema(description = "Reply delivery mode (voice|text); blank defaults to voice.",
                example = "voice") String replyMode,
        @Schema(description = "Escalation handoff reference riding the envelope (TASK-BE-036).",
                example = "handoff-7") String escalationContext) {

    public boolean hasTranscript() {
        return transcript != null && !transcript.isBlank();
    }

    // Maps the request onto the normalized channel envelope (TASK-BE-037). The memory/session key
    // prefers external_session_id (a Genesys call keys on its conversationId/participant) and falls
    // back to conversation_id so existing web callers keep their exact stateful behaviour.
    public ChannelEnvelope toEnvelope() {
        String sessionId = hasText(externalSessionId) ? externalSessionId : conversationId;
        return ChannelEnvelope.of(channel, sessionId, messageId, idempotencyKey, replyMode, escalationContext);
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
