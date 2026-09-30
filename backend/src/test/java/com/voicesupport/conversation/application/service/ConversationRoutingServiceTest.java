package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.RoutableTurn;
import com.voicesupport.conversation.domain.port.in.AnswerBillingQuestionUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.out.BillingIntentPort;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

// Routing rules (TASK-BE-061, ADR-0055): a turn goes to the deterministic billing chain ONLY when the
// channel supplied an account reference AND the turn is a billing question; otherwise it goes to RAG.
@DisplayName("ConversationRoutingService (channel-provided identity)")
class ConversationRoutingServiceTest {

    private final RecordingConverse converse = new RecordingConverse();
    private final RecordingBilling billing = new RecordingBilling();

    @Test
    void routes_to_billing_when_account_reference_present_and_billing_intent() {
        // GIVEN a billing question with a channel-provided account reference
        var router = new ConversationRoutingService(converse, billing, transcript -> true);
        var turn = new RoutableTurn("ma facture a augmenté", "conv-1", "fr", "99224964", "web_voice", "corr-1");

        // WHEN the turn is routed
        GeneratedAnswer answer = router.answer(turn);

        // THEN the billing chain answers with the account reference; RAG is not called
        assertThat(answer.text()).isEqualTo("billing answer");
        assertThat(billing.lastRequest.reference()).isEqualTo("99224964");
        assertThat(billing.lastRequest.transcript()).isEqualTo("ma facture a augmenté");
        assertThat(converse.calls).isZero();
    }

    @Test
    void routes_to_rag_when_no_account_reference_even_if_billing_intent() {
        // GIVEN a billing question but NO account reference ("no account" UI choice)
        var router = new ConversationRoutingService(converse, billing, transcript -> true);
        var turn = new RoutableTurn("ma facture a augmenté", "conv-1", "fr", null, "web_voice", "corr-1");

        // WHEN the turn is routed
        GeneratedAnswer answer = router.answer(turn);

        // THEN RAG answers; the billing chain is never invoked (fail-safe, no identity)
        assertThat(answer.text()).isEqualTo("rag answer");
        assertThat(converse.calls).isEqualTo(1);
        assertThat(billing.calls).isZero();
    }

    @Test
    void routes_to_rag_when_account_reference_present_but_not_a_billing_question() {
        // GIVEN a non-billing question even though an account reference is provided
        var router = new ConversationRoutingService(converse, billing, transcript -> false);
        var turn = new RoutableTurn("quels sont vos horaires ?", "conv-1", "fr", "99224964", "web_voice", "corr-1");

        // WHEN the turn is routed
        GeneratedAnswer answer = router.answer(turn);

        // THEN RAG answers; the billing chain is never invoked
        assertThat(answer.text()).isEqualTo("rag answer");
        assertThat(converse.calls).isEqualTo(1);
        assertThat(billing.calls).isZero();
    }

    @Test
    void forwards_the_forced_language_to_rag() {
        // GIVEN a non-billing turn with a forced language
        var router = new ConversationRoutingService(converse, billing, transcript -> false);
        var turn = new RoutableTurn("hello", "conv-1", "en", null, "web_voice", "corr-1");

        // WHEN routed
        router.answer(turn);

        // THEN the forced language reaches the RAG use case
        assertThat(converse.lastLanguage).isEqualTo("en");
        assertThat(converse.lastConversationId).isEqualTo("conv-1");
    }

    private static final class RecordingConverse implements ConverseUseCase {
        private int calls;
        private String lastConversationId;
        private String lastLanguage;

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId) {
            return converse(transcript, conversationId, null);
        }

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId, String forcedLanguage) {
            this.calls++;
            this.lastConversationId = conversationId;
            this.lastLanguage = forcedLanguage;
            return GeneratedAnswer.grounded("rag answer", 0.9);
        }
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
