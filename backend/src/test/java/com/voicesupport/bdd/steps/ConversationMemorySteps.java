package com.voicesupport.bdd.steps;

import com.voicesupport.conversation.application.service.AnswerService;
import com.voicesupport.conversation.application.service.ConversationService;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.fake.FakeAnswerGeneratorPort;
import com.voicesupport.conversation.fake.FakeGroundQueryUseCase;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.InMemoryConversationMemoryAdapter;
import io.cucumber.java.Before;
import io.cucumber.java.en.And;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class ConversationMemorySteps {

    private FakeGroundQueryUseCase grounding;
    private FakeAnswerGeneratorPort generator;
    private ConversationService service;

    @Before
    public void setUp() {
        grounding = new FakeGroundQueryUseCase();
        generator = new FakeAnswerGeneratorPort();
        AnswerService answerService = new AnswerService(grounding, generator, new OutputGuardrail());
        service = new ConversationService(answerService, new InMemoryConversationMemoryAdapter(6, 100));
    }

    @Given("a fresh conversation memory")
    public void freshConversationMemory() {
        // The @Before hook already builds an empty memory; this reads as intent in the feature.
    }

    @And("retrieval returns answerable evidence")
    public void retrievalReturnsAnswerableEvidence() {
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("La proration explique l'écart.", "billing-faq#1", "billing", 0.83))));
        generator.setNextAnswer("La proration explique l'écart de facturation.");
    }

    @When("the customer says {string} in conversation {string}")
    public void theCustomerSaysInConversation(String transcript, String conversationId) {
        service.converse(transcript, conversationId);
    }

    @And("the customer then says {string} in conversation {string}")
    public void theCustomerThenSaysInConversation(String transcript, String conversationId) {
        service.converse(transcript, conversationId);
    }

    @Then("the language model received the previous turn as context")
    public void llmReceivedPreviousTurn() {
        assertTrue(generator.lastHistory.contains("Client : Pourquoi ma facture change ?"),
                "expected the previous customer turn in the history");
        assertTrue(generator.lastHistory.contains("Assistant : La proration explique l'écart de facturation."),
                "expected the previous assistant turn in the history");
        assertFalse(generator.lastHistory.contains("Client : Et le mois prochain ?"),
                "the current turn must be excluded from the history");
    }

    @And("the follow-up is treated as an ongoing conversation")
    public void followUpIsOngoing() {
        assertTrue(grounding.lastAlreadyGreeted, "expected the follow-up to be flagged as already greeted");
    }

    @Then("the turn is treated as the start of the conversation")
    public void turnIsStartOfConversation() {
        assertFalse(grounding.lastAlreadyGreeted, "expected the first turn to allow greeting");
    }

    @And("the language model received no prior context")
    public void llmReceivedNoPriorContext() {
        assertTrue(generator.lastHistory.isEmpty(), "expected an empty history on the first turn");
    }

    @And("conversation {string} is treated as a fresh start")
    public void conversationIsFreshStart(String conversationId) {
        assertFalse(grounding.lastAlreadyGreeted, "expected the other conversation to start fresh");
    }
}
