package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import io.swagger.v3.oas.annotations.media.Schema;

// Dedicated billing-explanation contract (TASK-BE-045, ADR-0051 D3c). Wire field names are
// snake_case via the global Jackson strategy (e.g. invoice_id, conversation_id, correlation_id). The
// customer reference scopes identity resolution (BR-002-1) and is potentially personal data — it is
// never logged in clear. /converse is intentionally left untouched; routing billing from /converse is
// a follow-up ticket.
@Schema(description = "Billing-explanation turn: the transcript plus the identity reference and traceability ids.")
public record BillingExplainRequest(
        @Schema(description = "Customer utterance to explain (a billing question).",
                example = "Pourquoi ma facture a augmenté ce mois-ci ?") String transcript,
        @Schema(description = "Customer reference used to resolve the billing account (BR-002-1).",
                example = "EIR-1002") String reference,
        @Schema(description = "Optional invoice id; reserved (V1 compares the two most recent).")
        String invoiceId,
        @Schema(description = "Optional forced answer language (fr|en); blank keeps auto-detection.",
                example = "fr") String language,
        @Schema(description = "Conversation id for traceability; blank = stateless.", example = "conv-1234")
        String conversationId,
        @Schema(description = "Correlation id propagated across logs/metrics and echoed back.",
                example = "corr-abcd") String correlationId,
        @Schema(description = "Originating channel.", example = "web_voice") String channel) {

    public boolean hasTranscript() {
        return transcript != null && !transcript.isBlank();
    }

    public BillingExplanationRequest toDomainRequest() {
        return new BillingExplanationRequest(
                transcript, reference, invoiceId, language, channel, conversationId, correlationId);
    }
}
