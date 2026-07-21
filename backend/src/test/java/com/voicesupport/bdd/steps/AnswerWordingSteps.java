package com.voicesupport.bdd.steps;

import com.voicesupport.conversation.application.service.AnswerService;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.fake.FakeAnswerGeneratorPort;
import com.voicesupport.conversation.fake.FakeGroundQueryUseCase;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.cucumber.java.Before;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class AnswerWordingSteps {

    private FakeGroundQueryUseCase grounding;
    private FakeAnswerGeneratorPort generator;
    private AnswerService service;
    private GeneratedAnswer answer;
    private String llmReply;

    @Before
    public void setUp() {
        grounding = new FakeGroundQueryUseCase();
        generator = new FakeAnswerGeneratorPort();
        service = new AnswerService(
                grounding, generator, new OutputGuardrail(),
                new LanguageDetector(AnswerLanguage.ENGLISH), new BackendTelemetry(new SimpleMeterRegistry()));
        answer = null;
        llmReply = null;
    }

    @Given("retrieval returns strong billing evidence")
    public void retrievalReturnsStrongEvidence() {
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("La proration explique l'écart de facturation.", "billing-faq#1", "billing", 0.83))));
    }

    @Given("the grounding pipeline blocks the input as off-topic")
    public void groundingBlocksOffTopic() {
        grounding.setNextResult(GroundingResult.blocked(
                GuardrailDecision.offTopic("Cette question sort de mon domaine.")));
    }

    @Given("the language model would reply {string}")
    public void theLanguageModelWouldReply(String reply) {
        this.llmReply = reply;
        generator.setNextAnswer(reply);
    }

    @When("the customer asks the assistant {string}")
    public void theCustomerAsksTheAssistant(String question) {
        answer = service.answer(question, "billing", 4, true, java.util.List.of());
    }

    @Then("the assistant voices the generated answer")
    public void voicesGeneratedAnswer() {
        assertTrue(answer.grounded(), "expected a grounded answer");
        assertEquals(llmReply, answer.text());
    }

    @Then("the answer carries a confidence signal")
    public void answerCarriesConfidence() {
        assertNotNull(answer.confidence(), "expected a confidence signal");
    }

    @Then("the assistant does not voice the generated answer")
    public void doesNotVoiceGeneratedAnswer() {
        assertFalse(answer.grounded(), "expected a non-grounded fallback");
        if (llmReply != null) {
            assertFalse(llmReply.equals(answer.text()), "the raw LLM reply must not be voiced");
        }
        assertNull(answer.confidence(), "a fallback carries no confidence");
    }

    @Then("the assistant offers to reach a human advisor")
    public void offersHumanAdvisor() {
        assertTrue(answer.text().toLowerCase().contains("conseiller"),
                "expected a hand-off to a human advisor");
    }

    @Then("the language model is never called")
    public void languageModelNeverCalled() {
        assertEquals(0, generator.callCount, "expected the LLM to be skipped");
    }
}
