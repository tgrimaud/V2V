package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.WarmUpResult;

public record WarmUpResponse(
        boolean embeddingWarmed, boolean llmWarmed, boolean streamWarmed, boolean fullyWarmed, long durationMs) {

    public static WarmUpResponse from(WarmUpResult result) {
        return new WarmUpResponse(result.embeddingWarmed(), result.llmWarmed(),
                result.streamWarmed(), result.fullyWarmed(), result.durationMs());
    }
}
