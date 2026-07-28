package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import io.swagger.v3.oas.annotations.media.Schema;

// ADR-0021 conversation contract (matches the voice runtime's HttpBackendAdapter payload):
// the transcript to answer plus traceability ids and the originating channel.
@Schema(description = "Conversation turn: the transcript to answer plus traceability ids and channel.")
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
                example = "fr") String language) {

    public boolean hasTranscript() {
        return transcript != null && !transcript.isBlank();
    }

    public boolean hasConversationId() {
        return conversationId != null && !conversationId.isBlank();
    }
}
