package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("RetrievalConfidenceGuardrail (post-retrieval)")
class RetrievalConfidenceGuardrailTest {

    private final RetrievalConfidenceGuardrail guardrail = new RetrievalConfidenceGuardrail(0.5);

    @Test
    @DisplayName("blocks with low-confidence when no evidence was retrieved")
    void blocksWhenEmpty() {
        GuardrailDecision decision = guardrail.check("Ma question", List.of());

        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.LOW_CONFIDENCE, decision.verdict());
    }

    @Test
    @DisplayName("blocks when the best score is below the threshold")
    void blocksWhenWeak() {
        List<RetrievedEvidence> weak = List.of(
                new RetrievedEvidence("t1", "s1", "billing", 0.40),
                new RetrievedEvidence("t2", "s2", "billing", 0.35));

        GuardrailDecision decision = guardrail.check("Ma question", weak);

        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.LOW_CONFIDENCE, decision.verdict());
    }

    @Test
    @DisplayName("passes when at least one evidence reaches the threshold")
    void passesWhenStrong() {
        List<RetrievedEvidence> strong = List.of(
                new RetrievedEvidence("t1", "s1", "billing", 0.82),
                new RetrievedEvidence("t2", "s2", "billing", 0.30));

        GuardrailDecision decision = guardrail.check("Ma question", strong);

        assertFalse(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.PASS, decision.verdict());
    }

    @Test
    @DisplayName("applies a custom threshold")
    void appliesCustomThreshold() {
        RetrievalConfidenceGuardrail strict = new RetrievalConfidenceGuardrail(0.90);
        List<RetrievedEvidence> evidence = List.of(new RetrievedEvidence("t", "s", "billing", 0.85));

        GuardrailDecision decision = strict.check("q", evidence);

        assertTrue(decision.blocked());
    }
}
