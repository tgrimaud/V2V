package com.voicesupport.conversation.domain.model.valueobject;

import java.util.List;

// Input to prepare a hand-off (TASK-BE-036): the escalation reason plus the conversation context an
// advisor needs, assembled from the normalized channel envelope and the turn. Channel-agnostic — the
// same shape for web, WebRTC or Genesys (ADR-0009); the escalation decision already lives in the
// backend (the reason comes from a guardrail-blocked GeneratedAnswer, never from the channel).
public record EscalationHandoffCommand(
        String channel,
        String externalSessionId,
        String messageId,
        String conversationId,
        EscalationReason reason,
        String summary,
        String lastUserMessage,
        List<String> citations) {

    public EscalationHandoffCommand {
        if (reason == null) {
            throw new IllegalArgumentException("escalation reason must not be null");
        }
        citations = citations == null ? List.of() : List.copyOf(citations);
    }

    public static EscalationHandoffCommand of(ChannelEnvelope envelope, String question, GeneratedAnswer answer) {
        return new EscalationHandoffCommand(
                envelope.channel(),
                envelope.externalSessionId(),
                envelope.messageId(),
                envelope.conversationKey(),
                answer.escalation(),
                answer.text(),
                question,
                List.of());
    }
}
