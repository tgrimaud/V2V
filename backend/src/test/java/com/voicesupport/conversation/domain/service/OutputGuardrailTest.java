package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("OutputGuardrail (DEC-002: never voice an ungrounded amount)")
class OutputGuardrailTest {

    private final OutputGuardrail guardrail = new OutputGuardrail();

    @Test
    @DisplayName("an amount absent from the evidence is blocked as ungrounded")
    void fabricatedAmountBlocked() {
        // GIVEN evidence with no monetary amount
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("La proration explique l'écart de facturation.", "billing-faq#1", "billing", 0.8));

        // WHEN the LLM voices a specific amount
        GuardrailDecision decision = guardrail.check(
                "Combien je paie ?", "Votre facture est de 39,99 € ce mois-ci.", evidence);

        // THEN it is blocked with an ungrounded verdict and a safe hand-off message
        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.UNGROUNDED, decision.verdict());
        assertTrue(decision.fallbackMessage().toLowerCase().contains("conseiller"));
    }

    @Test
    @DisplayName("an amount backed by the evidence passes through")
    void groundedAmountPasses() {
        // GIVEN evidence that itself states the amount
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("L'abonnement Fibre est facturé 39,99 € par mois.", "billing-faq#2", "billing", 0.8));

        // WHEN the answer repeats that grounded amount
        GuardrailDecision decision = guardrail.check(
                "Quel est le prix de la Fibre ?", "L'offre Fibre coûte 39,99 € par mois.", evidence);

        // THEN it is not blocked
        assertFalse(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.PASS, decision.verdict());
    }

    @Test
    @DisplayName("an answer without any amount passes")
    void noAmountPasses() {
        // GIVEN any evidence
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("Redémarrez votre box pour rétablir la connexion.", "support-faq#1", "support", 0.8));

        // WHEN the answer contains no monetary amount
        GuardrailDecision decision = guardrail.check(
                "Ma box ne marche plus", "Redémarrez votre box puis patientez deux minutes.", evidence);

        // THEN it passes
        assertFalse(decision.blocked());
    }

    @Test
    @DisplayName("a blank answer is left to the caller (no false amount block)")
    void blankAnswerPasses() {
        // WHEN the generated answer is blank
        GuardrailDecision decision = guardrail.check("question", "  ", List.of());

        // THEN the guardrail passes (blank handling is the wording adapter's concern)
        assertFalse(decision.blocked());
    }

    @Test
    @DisplayName("an English question yields an English hand-off message")
    void englishFallback() {
        // GIVEN evidence with no amount and an English question
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("Billing is prorated for mid-cycle changes.", "billing-faq#3", "billing", 0.8));

        // WHEN the answer invents an amount
        GuardrailDecision decision = guardrail.check(
                "How much do I pay?", "Your bill is $42.00 this month.", evidence);

        // THEN the fallback is in English
        assertTrue(decision.blocked());
        assertTrue(decision.fallbackMessage().toLowerCase().contains("agent"));
    }
}
