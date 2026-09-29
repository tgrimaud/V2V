package com.voicesupport.conversation.domain.model.valueobject;

// A /converse turn as the router sees it (TASK-BE-061, ADR-0055): the transcript plus the memory key,
// the optional forced answer language, and the channel-provided customer identity context
// (accountReference) that lets a billing question route to the deterministic billing chain instead of
// RAG. accountReference simulates the target where the channel (e.g. Genesys ANI, an authenticated
// header/param) supplies identity up front; blank means no identity context -> always RAG.
public record RoutableTurn(String transcript, String conversationKey, String forcedLanguage,
        String accountReference, String channel, String correlationId) {

    public boolean hasAccountReference() {
        return accountReference != null && !accountReference.isBlank();
    }

    // Maps this turn to the billing chain's request (no invoice_id: the customer never quotes one).
    // Centralized here so the blocking and streaming routers build an identical request.
    public BillingExplanationRequest toBillingExplanationRequest() {
        return new BillingExplanationRequest(
                transcript, accountReference, null, forcedLanguage, channel, conversationKey, correlationId);
    }
}
