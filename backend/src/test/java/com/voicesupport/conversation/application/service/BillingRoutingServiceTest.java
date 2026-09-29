package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.RoutableTurn;
import com.voicesupport.conversation.domain.port.in.AnswerBillingQuestionUseCase;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

// Single source of truth for the RAG-vs-billing decision (TASK-BE-061 / BUG-027): billing ONLY when
// the channel supplied an account reference AND the turn is a billing question; otherwise empty.
@DisplayName("BillingRoutingService (shared routing decision)")
class BillingRoutingServiceTest {

    private final RecordingBilling billing = new RecordingBilling();

    @Test
    void returns_the_billing_answer_when_account_reference_present_and_billing_intent() {
        var router = new BillingRoutingService(billing, transcript -> true);
        var turn = new RoutableTurn("ma facture a augmenté", "conv-1", "fr", "99224964", "web_voice", "corr-1");

        Optional<GeneratedAnswer> answer = router.billingAnswer(turn);

        assertThat(answer).isPresent();
        assertThat(answer.get().text()).isEqualTo("billing answer");
        assertThat(billing.lastRequest.reference()).isEqualTo("99224964");
        assertThat(billing.lastRequest.transcript()).isEqualTo("ma facture a augmenté");
    }

    @Test
    void returns_empty_when_no_account_reference_even_if_billing_intent() {
        var router = new BillingRoutingService(billing, transcript -> true);
        var turn = new RoutableTurn("ma facture a augmenté", "conv-1", "fr", null, "web_voice", "corr-1");

        assertThat(router.billingAnswer(turn)).isEmpty();
        assertThat(billing.calls).isZero();
    }

    @Test
    void returns_empty_when_account_reference_present_but_not_a_billing_question() {
        var router = new BillingRoutingService(billing, transcript -> false);
        var turn = new RoutableTurn("quels sont vos horaires ?", "conv-1", "fr", "99224964", "web_voice", "corr-1");

        assertThat(router.billingAnswer(turn)).isEmpty();
        assertThat(billing.calls).isZero();
    }

    private static final class RecordingBilling implements AnswerBillingQuestionUseCase {
        private int calls;
        private BillingExplanationRequest lastRequest;

        @Override
        public GeneratedAnswer answer(BillingExplanationRequest request) {
            this.calls++;
            this.lastRequest = request;
            return GeneratedAnswer.grounded("billing answer", 0.9);
        }
    }
}
