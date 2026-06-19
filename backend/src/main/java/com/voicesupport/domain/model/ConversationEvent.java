package com.voicesupport.domain.model;

import java.time.Instant;

public record ConversationEvent(
        String conversationId,
        String channel,
        String question,
        String answer,
        int citationCount,
        long latencyMs,
        boolean escalated,
        Instant timestamp
) {
    public static ConversationEvent of(String conversationId, String channel, String question,
                                       String answer, int citationCount, long latencyMs, boolean escalated) {
        return new ConversationEvent(conversationId, channel, question, answer,
                citationCount, latencyMs, escalated, Instant.now());
    }
}
