package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
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
        GuardrailDecision decision = guardrail.check(List.of(), AnswerLanguage.FRENCH);

        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.LOW_CONFIDENCE, decision.verdict());
    }

    @Test
    @DisplayName("blocks when the best score is below the threshold")
    void blocksWhenWeak() {
        List<RetrievedEvidence> weak = List.of(
                new RetrievedEvidence("t1", "s1", "billing", 0.40),
                new RetrievedEvidence("t2", "s2", "billing", 0.35));

        GuardrailDecision decision = guardrail.check(weak, AnswerLanguage.FRENCH);

        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.LOW_CONFIDENCE, decision.verdict());
    }

    @Test
    @DisplayName("passes when at least one evidence reaches the threshold")
    void passesWhenStrong() {
        List<RetrievedEvidence> strong = List.of(
                new RetrievedEvidence("t1", "s1", "billing", 0.82),
                new RetrievedEvidence("t2", "s2", "billing", 0.30));

        GuardrailDecision decision = guardrail.check(strong, AnswerLanguage.FRENCH);

        assertFalse(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.PASS, decision.verdict());
    }

    @Test
    @DisplayName("applies a custom threshold")
    void appliesCustomThreshold() {
        RetrievalConfidenceGuardrail strict = new RetrievalConfidenceGuardrail(0.90);
        List<RetrievedEvidence> evidence = List.of(new RetrievedEvidence("t", "s", "billing", 0.85));

        GuardrailDecision decision = strict.check(evidence, AnswerLanguage.FRENCH);

        assertTrue(decision.blocked());
    }

    // ADR-0034 / BUG-005: three-band policy (floor 0.5, clarify ceiling 0.62).
    private final RetrievalConfidenceGuardrail banded = new RetrievalConfidenceGuardrail(0.5, 0.62);

    @Test
    @DisplayName("BUG-005: a middle-confidence retrieval (0.52) asks to clarify, not answer")
    void clarifiesOnMiddleConfidence() {
        List<RetrievedEvidence> middle = List.of(new RetrievedEvidence("t", "s", "support", 0.5213));

        GuardrailDecision decision = banded.check(middle, AnswerLanguage.FRENCH);

        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.CLARIFY, decision.verdict());
    }

    @Test
    @DisplayName("below the floor still hands off to an advisor (low confidence), not clarify")
    void handsOffBelowFloor() {
        List<RetrievedEvidence> weak = List.of(new RetrievedEvidence("t", "s", "support", 0.45));

        GuardrailDecision decision = banded.check(weak, AnswerLanguage.FRENCH);

        assertEquals(GuardrailDecision.Verdict.LOW_CONFIDENCE, decision.verdict());
    }

    @Test
    @DisplayName("at or above the clarify ceiling the answer passes")
    void passesAtOrAboveCeiling() {
        List<RetrievedEvidence> strong = List.of(new RetrievedEvidence("t", "s", "support", 0.76));

        assertEquals(GuardrailDecision.Verdict.PASS, banded.check(strong, AnswerLanguage.FRENCH).verdict());
    }

    @Test
    @DisplayName("the single-threshold constructor keeps the legacy no-clarify-band behavior")
    void singleThresholdHasNoClarifyBand() {
        RetrievalConfidenceGuardrail legacy = new RetrievalConfidenceGuardrail(0.5);
        List<RetrievedEvidence> middle = List.of(new RetrievedEvidence("t", "s", "support", 0.5213));

        assertEquals(GuardrailDecision.Verdict.PASS, legacy.check(middle, AnswerLanguage.FRENCH).verdict());
    }
}
