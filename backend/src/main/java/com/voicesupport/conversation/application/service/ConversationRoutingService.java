package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.RoutableTurn;
import com.voicesupport.conversation.domain.port.in.AnswerBillingQuestionUseCase;
import com.voicesupport.conversation.domain.port.in.ConversationRoutingUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.out.BillingIntentPort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Routes a /converse turn between the deterministic billing chain and the RAG pipeline (TASK-BE-061,
// ADR-0055). Billing is taken only when the channel supplied an account reference AND the turn is a
// billing question (deterministic intent guard via the seam). The account reference is a customer
// identifier (personal data): its value is never logged, only its presence and the route taken.
public class ConversationRoutingService implements ConversationRoutingUseCase {

    private static final Logger log = LoggerFactory.getLogger(ConversationRoutingService.class);

    private final ConverseUseCase converse;
    private final AnswerBillingQuestionUseCase billing;
    private final BillingIntentPort billingIntent;

    public ConversationRoutingService(
            ConverseUseCase converse, AnswerBillingQuestionUseCase billing, BillingIntentPort billingIntent) {
        this.converse = converse;
        this.billing = billing;
        this.billingIntent = billingIntent;
    }

    @Override
    public GeneratedAnswer answer(RoutableTurn turn) {
        boolean toBilling = routesToBilling(turn);
        log.info("[ROUTE] route={} account_ref_present={}", toBilling ? "billing" : "rag",
                turn.hasAccountReference());
        if (toBilling) {
            return billing.answer(toBillingRequest(turn));
        }
        return converse.converse(turn.transcript(), turn.conversationKey(), turn.forcedLanguage());
    }

    private boolean routesToBilling(RoutableTurn turn) {
        return turn.hasAccountReference() && billingIntent.isBillingQuestion(turn.transcript());
    }

    private static BillingExplanationRequest toBillingRequest(RoutableTurn turn) {
        return new BillingExplanationRequest(turn.transcript(), turn.accountReference(), null,
                turn.forcedLanguage(), turn.channel(), turn.conversationKey(), turn.correlationId());
    }
}
