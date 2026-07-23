package com.voicesupport.bdd.steps;

import com.voicesupport.conversation.application.service.AnswerService;
import com.voicesupport.conversation.application.service.RetrievalGroundingService;
import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.service.InputGuardrail;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.domain.service.RetrievalConfidenceGuardrail;
import com.voicesupport.conversation.fake.FakeKnowledgeRetrievalPort;
import com.voicesupport.conversation.infrastructure.adapter.out.llm.MistralAnswerAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.cucumber.java.en.And;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.chat.prompt.Prompt;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

// Product-observable QA for TASK-BE-018: drives the REAL grounding pipeline and the REAL
// answer adapter with a capturing fake ChatModel, so the concision budget is exercised end to
// end (config budget -> prompt sent to the model) instead of being asserted on internals. The
// canned model answer proves the grounded turn is still voiced; the captured system prompt
// proves the sentence cap is (or is not) instructed, in the customer's language.
public class AnswerConcisionSteps {

    private final CapturingChatModel model = new CapturingChatModel();
    private FakeKnowledgeRetrievalPort retrievalPort;
    private AnswerService service;
    private GeneratedAnswer answer;

    private void wire(int budget) {
        retrievalPort = new FakeKnowledgeRetrievalPort();
        BackendTelemetry telemetry = new BackendTelemetry(new SimpleMeterRegistry());
        MistralAnswerAdapter generator = new MistralAnswerAdapter(
                ChatClient.builder(model).build(), telemetry, 0, budget);
        RetrievalGroundingService grounding = new RetrievalGroundingService(
                new InputGuardrail(), new RetrievalConfidenceGuardrail(0.5), retrievalPort);
        service = new AnswerService(
                grounding, generator, new OutputGuardrail(),
                new LanguageDetector(AnswerLanguage.ENGLISH), telemetry);
        answer = null;
    }

    @Given("the assistant is configured to keep answers within {int} sentences")
    public void configuredWithBudget(int budget) {
        wire(budget);
    }

    @Given("the assistant is configured with the answer budget disabled")
    public void configuredDisabled() {
        wire(0);
    }

    @And("the knowledge base has relevant support content")
    public void relevantContent() {
        retrievalPort.setEvidence(List.of(new RetrievedEvidence(
                "Prorating explains the difference on your bill after a plan change.",
                "billing-faq#1", "billing", 0.83)));
    }

    @And("the knowledge base has no usable evidence")
    public void noUsableEvidence() {
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("loosely related snippet", "s1", "billing", 0.30)));
    }

    @When("the customer asks the concise bot {string}")
    public void theCustomerAsks(String question) {
        answer = service.answer(question, "billing", 4, true, List.of());
    }

    @Then("the assistant still voices a grounded answer")
    public void voicesGroundedAnswer() {
        assertTrue(answer.grounded(), "expected a grounded answer to be voiced");
        assertNotNull(answer.confidence(), "a grounded answer carries a confidence signal");
    }

    @Then("the assistant does not voice a grounded answer")
    public void doesNotVoiceGroundedAnswer() {
        assertFalse(answer.grounded(), "expected a non-grounded hand-off, not a voiced answer");
    }

    @And("a human advisor is offered")
    public void offersHumanAdvisor() {
        String text = answer.text().toLowerCase();
        assertTrue(text.contains("conseiller") || text.contains("advisor") || text.contains("agent"),
                "expected an offer to reach a human: " + answer.text());
    }

    @And("the wording request caps the answer at {int} sentences")
    public void wordingRequestCapsAt(int budget) {
        String system = model.lastSystemText();
        assertTrue(system.contains(budget + " sentence(s) maximum")
                        || system.contains(budget + " phrase(s) maximum"),
                "expected a sentence cap of " + budget + " in the prompt: " + system);
    }

    @And("the wording request carries no sentence cap")
    public void wordingRequestHasNoCap() {
        String system = model.lastSystemText();
        assertFalse(system.contains("sentence(s) maximum") || system.contains("phrase(s) maximum"),
                "expected no sentence cap when the budget is disabled: " + system);
    }

    @And("the concision instruction is written in {word}")
    public void concisionInstructionLanguage(String language) {
        String system = model.lastSystemText();
        if (language.equalsIgnoreCase("french")) {
            assertTrue(system.contains("phrase(s) maximum"), "expected a French concision cap: " + system);
        } else {
            assertTrue(system.contains("sentence(s) maximum"), "expected an English concision cap: " + system);
        }
    }

    // Minimal capturing ChatModel: records the last prompt so the concision instruction sent to
    // the provider can be asserted, and returns a fixed grounded answer (no hand-off marker) so
    // the grounded turn is still voiced by the OutputGuardrail.
    private static final class CapturingChatModel implements ChatModel {
        private volatile Prompt lastPrompt;

        @Override
        public ChatResponse call(Prompt prompt) {
            this.lastPrompt = prompt;
            return new ChatResponse(List.of(new Generation(
                    new AssistantMessage("This is explained by prorating after your recent plan change."))));
        }

        String lastSystemText() {
            assertNotNull(lastPrompt, "the language model was not called, so no prompt was captured");
            return lastPrompt.getInstructions().stream()
                    .filter(m -> m.getMessageType() == org.springframework.ai.chat.messages.MessageType.SYSTEM)
                    .map(Message::getText)
                    .reduce("", (a, b) -> a + "\n" + b);
        }
    }
}
