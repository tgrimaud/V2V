package com.voicesupport.conversation.domain.model.valueobject;

import java.time.Instant;
import java.util.List;

// The audited escalation hand-off payload (ADR-0019): the full context an advisor needs, including
// customer PII (last_user_message, customer_reference). Per DEC-013 this stays backend-owned and is
// served only by an access-controlled fetch keyed on the handoff_id — it never travels inline
// through the channel. Pure value object: it holds no channel-specific rule (ADR-0009). Built via
// the Builder because ADR-0019 mandates 15 fields, well past the readable-constructor budget.
public record EscalationHandoff(
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
        Instant createdAt) {

    public EscalationHandoff {
        citations = citations == null ? List.of() : List.copyOf(citations);
    }

    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private String conversationId;
        private String channel;
        private String externalSessionId;
        private String messageId;
        private String customerReference;
        private String currentAgentId;
        private String reasonCode;
        private String reasonLabel;
        private String priority;
        private String summary;
        private String lastUserMessage;
        private String evidenceStatus;
        private List<String> citations = List.of();
        private String recommendedNextAction;
        private Instant createdAt;

        public Builder conversationId(String value) {
            this.conversationId = value;
            return this;
        }

        public Builder channel(String value) {
            this.channel = value;
            return this;
        }

        public Builder externalSessionId(String value) {
            this.externalSessionId = value;
            return this;
        }

        public Builder messageId(String value) {
            this.messageId = value;
            return this;
        }

        public Builder customerReference(String value) {
            this.customerReference = value;
            return this;
        }

        public Builder currentAgentId(String value) {
            this.currentAgentId = value;
            return this;
        }

        public Builder reason(EscalationReason reason) {
            this.reasonCode = reason.code();
            this.reasonLabel = reason.label();
            this.priority = reason.priority();
            this.evidenceStatus = reason.evidenceStatus();
            this.recommendedNextAction = reason.recommendedNextAction();
            return this;
        }

        public Builder summary(String value) {
            this.summary = value;
            return this;
        }

        public Builder lastUserMessage(String value) {
            this.lastUserMessage = value;
            return this;
        }

        public Builder citations(List<String> value) {
            this.citations = value == null ? List.of() : List.copyOf(value);
            return this;
        }

        public Builder createdAt(Instant value) {
            this.createdAt = value;
            return this;
        }

        public EscalationHandoff build() {
            return new EscalationHandoff(conversationId, channel, externalSessionId, messageId,
                    customerReference, currentAgentId, reasonCode, reasonLabel, priority, summary,
                    lastUserMessage, evidenceStatus, citations, recommendedNextAction, createdAt);
        }
    }
}
