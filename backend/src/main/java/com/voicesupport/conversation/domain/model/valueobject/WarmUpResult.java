package com.voicesupport.conversation.domain.model.valueobject;

public record WarmUpResult(boolean embeddingWarmed, boolean llmWarmed, long durationMs) {

    public boolean fullyWarmed() {
        return embeddingWarmed && llmWarmed;
    }
}
