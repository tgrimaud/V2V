package com.voicesupport.conversation.domain.port.out;

// Conversation-owned outbound seam to the billing context's deterministic intent guard (TASK-BE-061,
// ADR-0052). Lets the router decide whether a turn is a billing question without the conversation
// domain depending on billing types; the infrastructure adapter maps it onto the billing published
// API (DetectBillingIntentUseCase).
public interface BillingIntentPort {

    boolean isBillingQuestion(String transcript);
}
