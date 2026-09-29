package com.voicesupport.billing.domain.port.in;

// Published billing API for the deterministic, no-LLM billing-intent guard (ADR-0052 D2a, TASK-BE-061).
// Exposes the intent decision so the conversation context can route a turn to the billing chain (via
// its own outbound seam) without referencing a billing internal service.
public interface DetectBillingIntentUseCase {

    boolean isBillingExplanationRequest(String transcript);
}
