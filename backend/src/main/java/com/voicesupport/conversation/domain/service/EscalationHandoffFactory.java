package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffCommand;

import java.time.Instant;

// Assembles the audited EscalationHandoff (ADR-0019) from a command: maps the escalation reason to
// its reason_code / label / priority / evidence_status / recommended_next_action and stamps
// created_at. Pure domain, channel-agnostic (ADR-0009) — no store, no clock, no Spring; the caller
// supplies the timestamp so the mapping is deterministic and unit-testable.
public class EscalationHandoffFactory {

    public EscalationHandoff build(EscalationHandoffCommand command, Instant createdAt) {
        return EscalationHandoff.builder()
                .conversationId(command.conversationId())
                .channel(command.channel())
                .externalSessionId(command.externalSessionId())
                .messageId(command.messageId())
                .reason(command.reason())
                .summary(command.summary())
                .lastUserMessage(command.lastUserMessage())
                .citations(command.citations())
                .createdAt(createdAt)
                .build();
    }
}
