package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.out.ClarifyingQuestionGeneratorPort;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.domain.service.ProblemOpenerDetector;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.InMemoryConversationMemoryAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("BillingDiagnosticConversationService (US-043 / TASK-BE-071: bounded billing clarify)")
class BillingDiagnosticConversationServiceTest {

    private static final String BILLING_OPENER = "J'ai un problème avec ma facture";
    private static final String FR_HANDOFF = "Je n'ai pas cette information, je vous transfère à un conseiller.";

    private FakeConverse answerDelegate;
    private FakeConverseStream streamDelegate;
    private InMemoryConversationMemoryAdapter memory;
    private FakeClarifyGenerator clarifyGenerator;
    private SimpleMeterRegistry meterRegistry;

    @BeforeEach
    void setUp() {
        answerDelegate = new FakeConverse();
        streamDelegate = new FakeConverseStream();
        memory = new InMemoryConversationMemoryAdapter(6, 100);
        clarifyGenerator = new FakeClarifyGenerator("Could you tell me a bit more about the problem?");
        meterRegistry = new SimpleMeterRegistry();
    }

    private BillingDiagnosticConversationService service(int maxQuestions) {
        return new BillingDiagnosticConversationService(
                answerDelegate, streamDelegate, memory, new ProblemOpenerDetector(), clarifyGenerator,
                new LanguageDetector(AnswerLanguage.FRENCH), new OutputGuardrail(),
                new BackendTelemetry(meterRegistry), maxQuestions);
    }

    @Test
    @DisplayName("an under-specified billing opener asks an LLM-worded clarify (delegate not called)")
    void first_billing_opener_asks_llm_clarify() {
        GeneratedAnswer answer = service(2).converse(BILLING_OPENER, "c1", null);

        assertEquals("Could you tell me a bit more about the problem?", answer.text());
        assertFalse(answer.grounded(), "a clarify is a non-grounded fallback");
        assertFalse(answer.requiresEscalation(), "a clarify is not an escalation");
        assertEquals(0, answerDelegate.calls, "the clarify must not reach the answer pipeline");
        assertEquals(1, clarifyGenerator.calls);
        assertEquals(1, memory.recentTurns("c1").size(), "the clarify turn is recorded in memory");
    }

    @Test
    @DisplayName("asks at most max-questions clarifies, then hands off to an advisor (configurable bound)")
    void bounds_clarifies_then_escalates() {
        BillingDiagnosticConversationService service = service(2);

        GeneratedAnswer first = service.converse(BILLING_OPENER, "c1", null);
        GeneratedAnswer second = service.converse(BILLING_OPENER, "c1", null);
        GeneratedAnswer third = service.converse(BILLING_OPENER, "c1", null);

        assertFalse(first.requiresEscalation(), "1st billing opener clarifies");
        assertFalse(second.requiresEscalation(), "2nd billing opener clarifies");
        assertTrue(third.requiresEscalation(), "the 3rd (cap reached) hands off");
        assertEquals(FR_HANDOFF, third.text());
        assertEquals(0, answerDelegate.calls, "the diagnostic never delegated on billing openers");
        assertEquals(2, clarifyGenerator.calls, "exactly max-questions LLM clarifies were asked");
    }

    @Test
    @DisplayName("the max-questions bound is configurable (max=1 escalates on the 2nd opener)")
    void bound_is_configurable() {
        BillingDiagnosticConversationService service = service(1);

        assertFalse(service.converse(BILLING_OPENER, "c1", null).requiresEscalation());
        assertTrue(service.converse(BILLING_OPENER, "c1", null).requiresEscalation());
    }

    @Test
    @DisplayName("max-questions <= 0 disables the diagnostic (billing opener flows to the normal pipeline)")
    void disabled_when_max_non_positive() {
        GeneratedAnswer answer = service(0).converse(BILLING_OPENER, "c1", null);

        assertEquals("DELEGATED", answer.text());
        assertEquals(1, answerDelegate.calls);
        assertEquals(0, clarifyGenerator.calls);
    }

    @Test
    @DisplayName("a non-opener turn flows to the normal pipeline (not intercepted)")
    void non_opener_proceeds() {
        GeneratedAnswer answer = service(2).converse("Comment changer mon mot de passe ?", "c1", null);

        assertEquals("DELEGATED", answer.text());
        assertEquals(1, answerDelegate.calls);
        assertEquals(0, clarifyGenerator.calls);
    }

    @Test
    @DisplayName("an explicit advisor request during a billing problem is not intercepted (BR5)")
    void human_request_proceeds() {
        GeneratedAnswer answer = service(2)
                .converse("J'ai un problème avec ma facture, je veux parler à un conseiller", "c1", null);

        assertEquals("DELEGATED", answer.text(), "the escalation path, not a clarify, must handle it");
        assertEquals(1, answerDelegate.calls);
        assertEquals(0, clarifyGenerator.calls);
    }

    @Test
    @DisplayName("an answerable billing opener with an amount anchor flows to the normal pipeline")
    void answerable_billing_opener_proceeds() {
        GeneratedAnswer answer = service(2)
                .converse("J'ai un problème : ma facture a augmenté de 10 euros", "c1", null);

        assertEquals("DELEGATED", answer.text());
        assertEquals(1, answerDelegate.calls);
    }

    @Test
    @DisplayName("the customer's clarifying answer ends the episode and reaches the normal pipeline")
    void clarifying_answer_proceeds_after_opener() {
        BillingDiagnosticConversationService service = service(2);
        service.converse(BILLING_OPENER, "c1", null);                 // clarify #1

        GeneratedAnswer answer = service.converse("Elle a augmenté ce mois-ci", "c1", null);

        assertEquals("DELEGATED", answer.text(), "a non-opener answer proceeds to retrieval");
        assertEquals(1, answerDelegate.calls);
    }

    @Test
    @DisplayName("DEC-002: a clarify that would voice an amount is dropped for a safe hand-off")
    void clarify_voicing_an_amount_is_blocked() {
        clarifyGenerator = new FakeClarifyGenerator("Is your bill 10 euros higher than usual?");

        GeneratedAnswer answer = service(2).converse(BILLING_OPENER, "c1", null);

        assertEquals(FR_HANDOFF, answer.text(), "the ungrounded-amount clarify is replaced by the hand-off");
        assertTrue(answer.requiresEscalation());
        assertFalse(answer.text().matches(".*\\d.*"), "no figure is voiced");
    }

    @Test
    @DisplayName("streaming: a billing opener emits the clarify as one chunk (stream delegate not consumed)")
    void streaming_billing_opener_emits_clarify() {
        List<String> chunks = new ArrayList<>();

        GeneratedAnswer answer = service(2).converseStream(BILLING_OPENER, "c1", null).consume(chunks::add);

        assertEquals(List.of("Could you tell me a bit more about the problem?"), chunks);
        assertFalse(answer.grounded());
        assertEquals(0, streamDelegate.calls, "the clarify must not reach the streaming pipeline");
        assertEquals(1, memory.recentTurns("c1").size());
    }

    @Test
    @DisplayName("streaming: a non-opener turn flows to the streaming pipeline")
    void streaming_non_opener_delegates() {
        List<String> chunks = new ArrayList<>();

        service(2).converseStream("Comment changer mon mot de passe ?", "c1", null).consume(chunks::add);

        assertEquals(1, streamDelegate.calls);
        assertEquals(List.of("DELEGATED-STREAM"), chunks);
    }

    @Test
    @DisplayName("records the billing_clarify telemetry so the dialogue is countable (US-043 analytics)")
    void records_billing_clarify_telemetry() {
        service(2).converse(BILLING_OPENER, "c1", null);

        assertNotNull(meterRegistry.find("voice_support.billing_clarify").tag("event", "asked").counter(),
                "an 'asked' billing_clarify counter must be emitted");
        assertEquals(1.0,
                meterRegistry.get("voice_support.billing_clarify").tag("event", "asked").counter().count());
    }

    // --- fakes -------------------------------------------------------------------------------

    private static final class FakeConverse implements ConverseUseCase {
        private int calls;

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId) {
            return converse(transcript, conversationId, null);
        }

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId, String forcedLanguage) {
            calls++;
            return GeneratedAnswer.grounded("DELEGATED", 0.9);
        }
    }

    private static final class FakeConverseStream implements ConverseStreamUseCase {
        private int calls;

        @Override
        public TokenStream converseStream(String transcript, String conversationId) {
            return converseStream(transcript, conversationId, null);
        }

        @Override
        public TokenStream converseStream(String transcript, String conversationId, String forcedLanguage) {
            calls++;
            return onChunk -> {
                onChunk.accept("DELEGATED-STREAM");
                return GeneratedAnswer.grounded("DELEGATED-STREAM", 0.9);
            };
        }
    }

    private static final class FakeClarifyGenerator implements ClarifyingQuestionGeneratorPort {
        private final String question;
        private int calls;

        private FakeClarifyGenerator(String question) {
            this.question = question;
        }

        @Override
        public String generateClarifyingQuestion(String question, List<String> history, AnswerLanguage language) {
            calls++;
            return this.question;
        }
    }
}
