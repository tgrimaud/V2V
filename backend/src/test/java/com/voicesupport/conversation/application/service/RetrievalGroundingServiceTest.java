package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.service.InputGuardrail;
import com.voicesupport.conversation.domain.service.RetrievalConfidenceGuardrail;
import com.voicesupport.conversation.fake.FakeKnowledgeRetrievalPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("RetrievalGroundingService (guardrails + retrieval, no LLM)")
class RetrievalGroundingServiceTest {

    private FakeKnowledgeRetrievalPort retrievalPort;
    private RetrievalGroundingService service;

    @BeforeEach
    void setUp() {
        retrievalPort = new FakeKnowledgeRetrievalPort();
        service = new RetrievalGroundingService(
                new InputGuardrail(), new RetrievalConfidenceGuardrail(0.5), retrievalPort);
    }

    @Test
    @DisplayName("in-domain question returns grounded evidence")
    void inDomainReturnsEvidence() {
        // GIVEN the knowledge context returns strong billing evidence
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("La proration explique l'écart", "billing-faq#1", "billing", 0.83)));

        // WHEN grounding an in-domain question
        GroundingResult result = service.ground(
                "Pourquoi ma facture est plus élevée ce mois-ci ?", "billing", 4, true, AnswerLanguage.FRENCH);

        // THEN it is answerable with the retrieved evidence
        assertTrue(result.answerable());
        assertEquals(1, result.evidence().size());
        assertEquals("billing-faq#1", result.evidence().get(0).sourceId());
    }

    @Test
    @DisplayName("off-topic question is refused before any retrieval (no LLM path)")
    void offTopicRefusedWithoutRetrieval() {
        // WHEN grounding an off-topic question
        GroundingResult result = service.ground("Quel temps fait-il demain ?", "billing", 4, true, AnswerLanguage.FRENCH);

        // THEN it is blocked and retrieval was never called
        assertFalse(result.answerable());
        assertEquals(GuardrailDecision.Verdict.OFF_TOPIC, result.decision().verdict());
        assertEquals(0, retrievalPort.callCount);
        assertTrue(result.evidence().isEmpty());
    }

    @Test
    @DisplayName("greeting is handled directly, without retrieval")
    void greetingHandledWithoutRetrieval() {
        // WHEN grounding a greeting
        GroundingResult result = service.ground("Bonjour", "billing", 4, false, AnswerLanguage.FRENCH);

        // THEN it is blocked with a greeting decision and no retrieval
        assertFalse(result.answerable());
        assertEquals(GuardrailDecision.Verdict.GREETING, result.decision().verdict());
        assertEquals(0, retrievalPort.callCount);
    }

    @Test
    @DisplayName("weak evidence triggers a low-confidence refusal after retrieval")
    void weakEvidenceRefused() {
        // GIVEN retrieval returns only weakly-scored evidence
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("vaguely related", "s1", "billing", 0.30)));

        // WHEN grounding an in-domain question
        GroundingResult result = service.ground(
                "Pourquoi ma facture est plus élevée ce mois-ci ?", "billing", 4, true, AnswerLanguage.FRENCH);

        // THEN retrieval ran but the answer is blocked as low-confidence
        assertEquals(1, retrievalPort.callCount);
        assertFalse(result.answerable());
        assertEquals(GuardrailDecision.Verdict.LOW_CONFIDENCE, result.decision().verdict());
    }

    @Test
    @DisplayName("shared (general) evidence is included and can ground an answer")
    void generalEvidenceIncluded() {
        // GIVEN retrieval returns a shared 'general' chunk with a strong score
        retrievalPort.setEvidence(List.of(
                new RetrievedEvidence("Contact et horaires du support", "general-faq#1", "general", 0.77)));

        // WHEN grounding an in-domain question
        GroundingResult result = service.ground("Comment contacter le support ?", "support", 4, true, AnswerLanguage.FRENCH);

        // THEN the general chunk grounds an answerable result
        assertTrue(result.answerable());
        assertEquals("general", result.evidence().get(0).domain());
    }
}
