package com.voicesupport.bdd.steps;

import com.voicesupport.conversation.application.service.RetrievalGroundingService;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.service.InputGuardrail;
import com.voicesupport.conversation.domain.service.RetrievalConfidenceGuardrail;
import com.voicesupport.conversation.fake.FakeKnowledgeRetrievalPort;
import io.cucumber.java.Before;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class ConversationGroundingSteps {

    private FakeKnowledgeRetrievalPort retrievalPort;
    private RetrievalGroundingService service;
    private GroundingResult result;

    @Before
    public void setUp() {
        retrievalPort = new FakeKnowledgeRetrievalPort();
        service = new RetrievalGroundingService(
                new InputGuardrail(), new RetrievalConfidenceGuardrail(0.5), retrievalPort);
        result = null;
    }

    @Given("the knowledge base can return billing evidence with a strong match")
    public void billingEvidenceStrong() {
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("La proration explique l'écart", "billing-faq#1", "billing", 0.83)));
    }

    @Given("the knowledge base can only return weakly-matching evidence")
    public void weakEvidence() {
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("vaguement lié", "s1", "billing", 0.30)));
    }

    @Given("the knowledge base returns a shared general article with a strong match")
    public void generalEvidenceStrong() {
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("Service client joignable 8h-20h", "general-faq#1", "general", 0.77)));
    }

    @When("the customer asks {string}")
    public void theCustomerAsks(String question) {
        result = service.ground(question, "billing", 4, true);
    }

    @When("the customer says {string}")
    public void theCustomerSays(String question) {
        result = service.ground(question, "billing", 4, false);
    }

    @Then("the assistant is allowed to answer")
    public void allowedToAnswer() {
        assertTrue(result.answerable(), "expected an answerable result");
    }

    @Then("the answer is grounded in retrieved evidence")
    public void groundedInEvidence() {
        assertFalse(result.evidence().isEmpty(), "expected grounding evidence");
    }

    @Then("the answer includes shared general knowledge")
    public void includesGeneralKnowledge() {
        assertTrue(result.evidence().stream().anyMatch(e -> "general".equals(e.domain())),
                "expected a shared general chunk in the evidence");
    }

    @Then("the assistant refuses with an off-topic message")
    public void refusesOffTopic() {
        assertRefused(GuardrailDecision.Verdict.OFF_TOPIC);
    }

    @Then("the assistant refuses as inappropriate")
    public void refusesInappropriate() {
        assertRefused(GuardrailDecision.Verdict.INAPPROPRIATE);
    }

    @Then("the assistant replies with a greeting")
    public void repliesGreeting() {
        assertRefused(GuardrailDecision.Verdict.GREETING);
    }

    @Then("the assistant refuses with a low-confidence message")
    public void refusesLowConfidence() {
        assertRefused(GuardrailDecision.Verdict.LOW_CONFIDENCE);
    }

    @Then("no knowledge retrieval is performed")
    public void noRetrieval() {
        assertEquals(0, retrievalPort.callCount, "expected no retrieval call");
    }

    @Then("knowledge retrieval was attempted")
    public void retrievalAttempted() {
        assertEquals(1, retrievalPort.callCount, "expected exactly one retrieval call");
    }

    private void assertRefused(GuardrailDecision.Verdict expected) {
        assertFalse(result.answerable(), "expected a blocked result");
        assertEquals(expected, result.decision().verdict());
        assertFalse(result.decision().fallbackMessage() == null || result.decision().fallbackMessage().isBlank(),
                "expected a non-empty fallback message");
    }
}
