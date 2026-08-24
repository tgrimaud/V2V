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
                "Votre facture est de 39,99 € ce mois-ci.", evidence, AnswerLanguage.FRENCH);

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
                "L'offre Fibre coûte 39,99 € par mois.", evidence, AnswerLanguage.FRENCH);

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
                "Redémarrez votre box puis patientez deux minutes.", evidence, AnswerLanguage.FRENCH);

        // THEN it passes
        assertFalse(decision.blocked());
    }

    @Test
    @DisplayName("a blank answer is surfaced as a safe hand-off, not a grounded answer")
    void blankAnswerBlocked() {
        // WHEN the generated answer is blank
        GuardrailDecision decision = guardrail.check("  ", List.of(), AnswerLanguage.FRENCH);

        // THEN it is blocked with a low-confidence hand-off (never voiced as grounded)
        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.LOW_CONFIDENCE, decision.verdict());
        assertTrue(decision.fallbackMessage().toLowerCase().contains("conseiller"));
    }

    @Test
    @DisplayName("an explicit transfer/refusal answer is surfaced as a hand-off")
    void refusalAnswerBlocked() {
        // GIVEN evidence with no amount and the model emits the canned transfer sentence
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("Contenu de support.", "support-faq#1", "support", 0.8));

        // WHEN the answer is the instructed refusal
        GuardrailDecision decision = guardrail.check(
                "Je n'ai pas cette information, je vous transfère à un conseiller.", evidence, AnswerLanguage.FRENCH);

        // THEN it is blocked rather than reported as a grounded answer
        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.LOW_CONFIDENCE, decision.verdict());
    }

    @Test
    @DisplayName("an English transfer/refusal answer is caught like the French one (TASK-BE-015)")
    void englishRefusalAnswerBlocked() {
        // GIVEN evidence and the model emits the English instructed refusal
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("Support content.", "support-faq#1", "support", 0.8));

        // WHEN the answer is the English hand-off sentence
        GuardrailDecision decision = guardrail.check(
                "I don't have this information, I'll transfer you to an advisor.", evidence, AnswerLanguage.ENGLISH);

        // THEN it is blocked as a hand-off, not reported as a grounded answer
        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.LOW_CONFIDENCE, decision.verdict());
    }

    @Test
    @DisplayName("a fabricated amount that digit-collides with a grounded one is still blocked (DEC-002 bypass fix)")
    void digitCollisionBlocked() {
        // GIVEN evidence stating 150 € (canonical EUR:150.00)
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("Le forfait est facturé 150 € par mois.", "billing-faq#4", "billing", 0.8));

        // WHEN the answer voices 1,50 € — which the old digit-only key collapsed to the same "150"
        GuardrailDecision decision = guardrail.check(
                "Votre remise est de 1,50 € ce mois-ci.", evidence, AnswerLanguage.FRENCH);

        // THEN it is blocked as ungrounded (1.50 != 150.00)
        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.UNGROUNDED, decision.verdict());
    }

    @Test
    @DisplayName("the same amount in a different locale format matches the grounded evidence")
    void crossLocaleAmountMatches() {
        // GIVEN evidence with a French-formatted grouped+decimal amount 1.234,56 €
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("Le total annuel est de 1.234,56 € pour cette offre.", "billing-faq#5", "billing", 0.8));

        // WHEN the answer repeats it in English format €1,234.56
        GuardrailDecision decision = guardrail.check(
                "Le total annuel s'élève à €1,234.56.", evidence, AnswerLanguage.FRENCH);

        // THEN it passes: both normalize to EUR:1234.56
        assertFalse(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.PASS, decision.verdict());
    }

    @Test
    @DisplayName("the same digits in a different currency do not match (currency class is part of the key)")
    void differentCurrencyDoesNotMatch() {
        // GIVEN evidence stating 50 € (EUR:50.00)
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("Les frais de mise en service sont de 50 €.", "billing-faq#6", "billing", 0.8));

        // WHEN the answer voices $50 (USD:50.00)
        GuardrailDecision decision = guardrail.check(
                "The setup fee is $50.", evidence, AnswerLanguage.ENGLISH);

        // THEN it is blocked: same digits, different currency class
        assertTrue(decision.blocked());
        assertEquals(GuardrailDecision.Verdict.UNGROUNDED, decision.verdict());
    }

    @Test
    @DisplayName("an English-decided turn yields an English hand-off message")
    void englishFallback() {
        // GIVEN evidence with no amount and an English question
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("Billing is prorated for mid-cycle changes.", "billing-faq#3", "billing", 0.8));

        // WHEN the answer invents an amount
        GuardrailDecision decision = guardrail.check(
                "Your bill is $42.00 this month.", evidence, AnswerLanguage.ENGLISH);

        // THEN the fallback is in English
        assertTrue(decision.blocked());
        assertTrue(decision.fallbackMessage().toLowerCase().contains("agent"));
    }
}
