package com.voicesupport.conversation.domain.model.valueobject;

// A billing-explanation turn as the answer engine sees it (TASK-BE-045, ADR-0051): the transcript to
// answer, the channel + customer reference that scope identity resolution (BR-002-1), an optional
// invoice id, the resolved answer-language code, and the traceability ids. Conversation-owned so the
// answer engine never depends on the billing context's types; the outbound seam maps it across.
public record BillingExplanationRequest(String transcript, String reference, String invoiceId,
        String languageCode, String channel, String conversationId, String correlationId) {

    // Returns a copy with the answer-language resolved for the turn, so the deterministic explanation
    // is composed in the language the assistant will actually speak.
    public BillingExplanationRequest withLanguage(String resolvedLanguageCode) {
        return new BillingExplanationRequest(
                transcript, reference, invoiceId, resolvedLanguageCode, channel, conversationId, correlationId);
    }
}
