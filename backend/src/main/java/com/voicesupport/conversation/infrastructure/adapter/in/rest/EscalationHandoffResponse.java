package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import io.swagger.v3.oas.annotations.media.Schema;

import java.util.List;

// Audited hand-off payload served by reference (TASK-BE-036 / ADR-0019). Serialized snake_case via
// the global Jackson config; null fields (e.g. customer_reference, current_agent_id) are omitted by
// the NON_NULL policy. This full payload — including customer PII — is returned ONLY by the
// access-controlled fetch endpoint, never inline on the channel (DEC-013).
@Schema(description = "Full audited escalation hand-off payload (ADR-0019), fetched by handoff_id.")
public record EscalationHandoffResponse(
        String handoffId,
        String conversationId,
        String channel,
        String externalSessionId,
        String messageId,
        String customerReference,
        String currentAgentId,
        String reasonCode,
        String reasonLabel,
        String priority,
        String summary,
        String lastUserMessage,
        String evidenceStatus,
        List<String> citations,
        String recommendedNextAction,
        String createdAt) {

    public static EscalationHandoffResponse from(HandoffId id, EscalationHandoff handoff) {
        return new EscalationHandoffResponse(
                id.value(),
                handoff.conversationId(),
                handoff.channel(),
                handoff.externalSessionId(),
                handoff.messageId(),
                handoff.customerReference(),
                handoff.currentAgentId(),
                handoff.reasonCode(),
                handoff.reasonLabel(),
                handoff.priority(),
                handoff.summary(),
                handoff.lastUserMessage(),
                handoff.evidenceStatus(),
                handoff.citations(),
                handoff.recommendedNextAction(),
                handoff.createdAt() == null ? null : handoff.createdAt().toString());
    }
}
