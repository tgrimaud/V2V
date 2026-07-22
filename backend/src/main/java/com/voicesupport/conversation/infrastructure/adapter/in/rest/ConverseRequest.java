package com.voicesupport.conversation.infrastructure.adapter.in.rest;

// ADR-0021 conversation contract (matches the voice runtime's HttpBackendAdapter payload):
// the transcript to answer plus traceability ids and the originating channel.
public record ConverseRequest(
        String transcript,
        String conversationId,
        String correlationId,
        String channel,
        // US-042: optional UI-selected language ("fr"/"en"); when present it forces the answer
        // language, overriding backend auto-detection. Null/blank keeps detection behavior.
        String language) {

    public boolean hasTranscript() {
        return transcript != null && !transcript.isBlank();
    }

    public boolean hasConversationId() {
        return conversationId != null && !conversationId.isBlank();
    }
}
