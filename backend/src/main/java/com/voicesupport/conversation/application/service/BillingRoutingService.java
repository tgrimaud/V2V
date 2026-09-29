package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.RoutableTurn;
import com.voicesupport.conversation.domain.port.in.AnswerBillingQuestionUseCase;
import com.voicesupport.conversation.domain.port.out.BillingIntentPort;

import java.util.Optional;

// Single source of truth for the RAG-vs-billing routing decision (TASK-BE-061 / BUG-027, ADR-0055),
// shared by the blocking /converse path (ConversationRoutingService) and the streaming
// /converse-stream path (ConverseStreamSession). A turn is answered by the deterministic billing
// chain ONLY when the channel supplied an account reference AND the turn is a billing question;
// otherwise the caller keeps its own default (RAG). Returning an Optional lets the streaming path
// stream RAG tokens on a miss while emitting the pre-computed grounded billing text on a hit.
public class BillingRoutingService {

    private final AnswerBillingQuestionUseCase billing;
    private final BillingIntentPort billingIntent;

    public BillingRoutingService(AnswerBillingQuestionUseCase billing, BillingIntentPort billingIntent) {
        this.billing = billing;
        this.billingIntent = billingIntent;
    }

    public Optional<GeneratedAnswer> billingAnswer(RoutableTurn turn) {
        if (turn.hasAccountReference() && billingIntent.isBillingQuestion(turn.transcript())) {
            return Optional.of(billing.answer(turn.toBillingExplanationRequest()));
        }
        return Optional.empty();
    }
}
