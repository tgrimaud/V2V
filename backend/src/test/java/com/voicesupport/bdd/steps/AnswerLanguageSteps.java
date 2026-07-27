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
import com.voicesupport.conversation.fake.FakeAnswerGeneratorPort;
import com.voicesupport.conversation.fake.FakeKnowledgeRetrievalPort;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.cucumber.java.Before;
import io.cucumber.java.en.And;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

// Product-observable QA for TASK-BE-015: drives the REAL grounding pipeline (InputGuardrail +
// RetrievalConfidenceGuardrail) and AnswerService with a fake LLM, so the language decision is
// exercised end-to-end and not fed in. A grounded turn is "answered in X" when the assistant
// instructs the LLM in language X; a fallback/refusal turn is checked on the deterministic
// message text itself (detected language + escalation offer).
public class AnswerLanguageSteps {

    private FakeKnowledgeRetrievalPort retrievalPort;
    private FakeAnswerGeneratorPort generator;
    private AnswerService service;
    private final List<String> history = new ArrayList<>();
    private GeneratedAnswer answer;

    @Before
    public void setUp() {
        retrievalPort = new FakeKnowledgeRetrievalPort();
        generator = new FakeAnswerGeneratorPort();
        RetrievalGroundingService grounding = new RetrievalGroundingService(
                new InputGuardrail(), new RetrievalConfidenceGuardrail(0.5), retrievalPort);
        service = new AnswerService(
                grounding, generator, new OutputGuardrail(),
                new LanguageDetector(AnswerLanguage.ENGLISH), new BackendTelemetry(new SimpleMeterRegistry()));
        history.clear();
        answer = null;
    }

    @Given("the knowledge base has relevant English support content")
    public void relevantEnglishContent() {
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("Prorating explains the difference on your bill after a plan change.",
                        "billing-faq#1", "billing", 0.83)));
    }

    @Given("the knowledge base has relevant French support content")
    public void relevantFrenchContent() {
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("La proration explique l'écart sur votre facture après un changement d'offre.",
                        "billing-faq#1", "billing", 0.83)));
    }

    @Given("the assistant cannot find enough evidence to answer")
    public void notEnoughEvidence() {
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("loosely related snippet", "s1", "billing", 0.30)));
    }

    @And("the conversation so far has been in French")
    public void conversationSoFarInFrench() {
        history.add("Client : Pourquoi ma facture a-t-elle augmenté ce mois-ci ?");
        history.add("Assistant : La hausse vient de la proration lors de votre changement d'offre.");
    }

    @When("the customer's turn is {string}")
    public void theCustomersTurnIs(String question) {
        answer = service.answer(question, "billing", 4, true, List.copyOf(history));
    }

    @Then("the assistant answers in {word}")
    public void theAssistantAnswersIn(String language) {
        assertEquals(1, generator.callCount, "expected the assistant to word a grounded answer");
        assertEquals(languageFor(language), generator.lastLanguage,
                "the assistant must instruct the LLM in the customer's language");
    }

    @Then("the assistant's spoken reply is in {word}")
    public void theSpokenReplyIsIn(String language) {
        AnswerLanguage detected = AnswerLanguage.detect(answer.text())
                .orElseThrow(() -> new AssertionError("could not detect a language in: " + answer.text()));
        assertEquals(languageFor(language), detected,
                "the spoken fallback/refusal must be in the customer's language: " + answer.text());
    }

    @And("the assistant offers a human advisor")
    public void offersHumanAdvisor() {
        String text = answer.text().toLowerCase();
        assertTrue(text.contains("conseiller") || text.contains("advisor") || text.contains("agent"),
                "expected an offer to reach a human: " + answer.text());
    }

    @And("the assistant asks the customer to clarify")
    public void asksToClarify() {
        String text = answer.text().toLowerCase();
        assertTrue(text.contains("reformuler") || text.contains("rephrase")
                        || text.contains("préciser") || text.contains("more detail"),
                "expected a clarification prompt: " + answer.text());
    }

    private AnswerLanguage languageFor(String label) {
        return switch (label.toLowerCase()) {
            case "english" -> AnswerLanguage.ENGLISH;
            case "french" -> AnswerLanguage.FRENCH;
            default -> throw new IllegalArgumentException("unsupported language label: " + label);
        };
    }
}
