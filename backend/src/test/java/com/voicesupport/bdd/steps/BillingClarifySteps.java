package com.voicesupport.bdd.steps;

import com.voicesupport.conversation.application.service.BillingDiagnosticConversationService;
import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.out.ClarifyingQuestionGeneratorPort;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.domain.service.ProblemOpenerDetector;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.InMemoryConversationMemoryAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.cucumber.java.Before;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

// US-043 increment C product-acceptance glue: drives the real BillingDiagnosticConversationService
// decorator over fakes for the two converse delegates and the LLM clarify generator, with the real
// conversation memory, opener detector, output guardrail, language detector and telemetry — so the
// bounded, DEC-002-safe, language-aware clarify dialogue is validated as product-observable behaviour.
public class BillingClarifySteps {

    private static final String CONVERSATION = "qa-billing-clarify";
    private static final String FR_HANDOFF = "Je n'ai pas cette information, je vous transfère à un conseiller.";
    private static final String FR_CLARIFY = "Pouvez-vous préciser le problème ?";

    private FakeConverse answerDelegate;
    private FakeConverseStream streamDelegate;
    private FakeClarify clarifyGenerator;
    private InMemoryConversationMemoryAdapter memory;
    private int maxQuestions;
    private GeneratedAnswer answer;

    @Before
    public void setUp() {
        answerDelegate = new FakeConverse();
        streamDelegate = new FakeConverseStream();
        clarifyGenerator = new FakeClarify();
        memory = new InMemoryConversationMemoryAdapter(6, 100);
        maxQuestions = 2;
        answer = null;
    }

    @Given("the billing clarifying budget is {int} questions")
    public void theBudgetIs(int max) {
        maxQuestions = max;
    }

    @Given("the customer has already been asked {int} clarifying billing questions")
    public void alreadyAsked(int count) {
        for (int i = 0; i < count; i++) {
            memory.append(CONVERSATION, new ConversationTurn("J'ai un problème avec ma facture", FR_CLARIFY));
        }
    }

    @Given("the language model would propose a clarifying question mentioning an amount")
    public void llmWouldMentionAmount() {
        clarifyGenerator.withAmount = true;
    }

    @When("the customer sends {string}")
    public void theCustomerSends(String transcript) {
        answer = service().converse(transcript, CONVERSATION, null);
    }

    @Then("the assistant asks a clarifying billing question")
    public void asksClarifyingQuestion() {
        assertFalse(answer.requiresEscalation(), "a clarify is not an escalation");
        assertTrue(clarifyGenerator.calls >= 1, "the LLM clarify wording must have been requested");
        assertEquals(0, answerDelegate.calls, "a clarify must not reach the answer pipeline");
    }

    @Then("it does not answer from the knowledge base yet")
    public void doesNotAnswerYet() {
        assertEquals(0, answerDelegate.calls, "the normal answer pipeline must not run on a clarify turn");
    }

    @Then("the assistant offers to transfer the customer to a human advisor")
    public void offersHumanAdvisor() {
        assertTrue(answer.requiresEscalation(), "expected an escalation to a human advisor");
        assertEquals(FR_HANDOFF, answer.text());
    }

    @Then("it does not ask another clarifying question")
    public void doesNotAskAnother() {
        assertEquals(0, clarifyGenerator.calls, "at the cap no further clarify is generated");
    }

    @Then("the assistant answers from the knowledge base")
    public void answersFromKnowledgeBase() {
        assertEquals("ANSWER", answer.text(), "the turn must reach the normal answer pipeline");
        assertEquals(1, answerDelegate.calls);
        assertEquals(0, clarifyGenerator.calls, "an answerable turn is not clarified");
    }

    @Then("the clarifying flow does not intercept the turn")
    public void doesNotIntercept() {
        assertEquals(1, answerDelegate.calls, "the escalation path, not the clarify flow, must handle it");
        assertEquals(0, clarifyGenerator.calls);
    }

    @Then("the clarifying question is in French")
    public void questionIsFrench() {
        assertEquals(FR_CLARIFY, answer.text(), "the clarify must follow the French session language");
    }

    @Then("the response contains no amount")
    public void responseHasNoAmount() {
        assertFalse(answer.text().matches(".*\\d.*"), "no figure may be voiced (DEC-002): " + answer.text());
    }

    private BillingDiagnosticConversationService service() {
        return new BillingDiagnosticConversationService(
                answerDelegate, streamDelegate, memory, new ProblemOpenerDetector(), clarifyGenerator,
                new LanguageDetector(AnswerLanguage.FRENCH), new OutputGuardrail(),
                new BackendTelemetry(new SimpleMeterRegistry()), maxQuestions);
    }

    private static final class FakeConverse implements ConverseUseCase {
        private int calls;

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId) {
            return converse(transcript, conversationId, null);
        }

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId, String forcedLanguage) {
            calls++;
            return GeneratedAnswer.grounded("ANSWER", 0.9);
        }
    }

    private static final class FakeConverseStream implements ConverseStreamUseCase {
        @Override
        public TokenStream converseStream(String transcript, String conversationId) {
            return converseStream(transcript, conversationId, null);
        }

        @Override
        public TokenStream converseStream(String transcript, String conversationId, String forcedLanguage) {
            return onChunk -> {
                onChunk.accept("ANSWER");
                return GeneratedAnswer.grounded("ANSWER", 0.9);
            };
        }
    }

    private static final class FakeClarify implements ClarifyingQuestionGeneratorPort {
        private boolean withAmount;
        private int calls;

        @Override
        public String generateClarifyingQuestion(String question, List<String> history, AnswerLanguage language) {
            calls++;
            if (withAmount) {
                return language == AnswerLanguage.FRENCH
                        ? "Votre facture a-t-elle augmenté de 10 euros ?"
                        : "Did your bill go up by 10 euros?";
            }
            return language == AnswerLanguage.FRENCH ? FR_CLARIFY : "Could you tell me more about the problem?";
        }
    }
}
