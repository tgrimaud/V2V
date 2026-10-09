package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.service.ProblemOpenerDetector.Topic;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DisplayName("ProblemOpenerDetector (BUG-025)")
class ProblemOpenerDetectorTest {

    private final ProblemOpenerDetector detector = new ProblemOpenerDetector();

    @ParameterizedTest
    @ValueSource(strings = {
            "J'ai un problème avec ma facture",
            "Il y a un souci de facturation",
            "I have a problem with my bill",
            "There is an issue with my invoice",
            "ma facture",
            "my bill"})
    @DisplayName("classifies a generic billing opener as BILLING")
    void detects_billing_opener(String opener) {
        assertEquals(Optional.of(Topic.BILLING), detector.detect(opener), "opener: " + opener);
    }

    @ParameterizedTest
    @ValueSource(strings = {"J'ai un problème", "J'ai besoin d'aide", "Aidez-moi", "I need help", "I have an issue"})
    @DisplayName("classifies a topic-less problem/help opener as GENERAL")
    void detects_general_opener(String opener) {
        assertEquals(Optional.of(Topic.GENERAL), detector.detect(opener), "opener: " + opener);
    }

    @ParameterizedTest
    @ValueSource(strings = {
            // Still bypassed to retrieval: a BILLING opener carrying a concrete AMOUNT anchor is
            // answerable (number or spelled-out "euro(s)"), and a non-billing opener keeps the
            // GENERAL "any question marker bypasses" rule unchanged (US-043 / TASK-BE-070 D).
            "J'ai un problème : ma facture a augmenté de 10 euros",
            "J'ai un souci, ma facture a monté de cinq euros",
            "J'ai un problème, pourquoi donc ?",
            "Combien coûte le forfait fibre ?"})
    @DisplayName("does not flag an answerable question (billing amount anchor, or non-billing marker)")
    void ignores_specific_question(String question) {
        assertEquals(Optional.empty(), detector.detect(question), "question: " + question);
    }

    @ParameterizedTest
    @ValueSource(strings = {
            // US-043 / TASK-BE-070 (increment D): an under-specified BILLING opener now reaches the
            // clarify even with a WEAK interrogative marker and no amount anchor, instead of being
            // answered too directly. A mutant that keeps the old "any marker bypasses" billing rule
            // (or drops the CONCRETE_BILLING_ANCHOR guard) is caught here and by ignores_specific_question.
            "Pourquoi ai-je un problème de facturation ?",
            "How do I fix the problem with my bill?",
            "J'ai un problème avec ma facture, pourquoi ?"})
    @DisplayName("US-043: flags an under-specified billing opener with a weak marker as BILLING")
    void flags_underspecified_billing_opener_with_weak_marker(String opener) {
        assertEquals(Optional.of(Topic.BILLING), detector.detect(opener), "opener: " + opener);
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "Ma box internet ne fonctionne plus",
            "Quel est le tarif de l'abonnement fibre ?",
            "ok facture",
            ""})
    @DisplayName("does not flag a non-opener turn")
    void ignores_non_opener(String turn) {
        assertEquals(Optional.empty(), detector.detect(turn), "turn: " + turn);
    }

    @ParameterizedTest
    @ValueSource(strings = {
            // An explicit human/advisor request must NOT be intercepted, even with a problem word —
            // it flows to the pipeline so the escalation path (ADR-0019) can handle it.
            "J'ai un problème, je veux parler à un conseiller",
            "I have a problem, I want to speak to a human",
            "J'ai un souci, transférez-moi à un agent"})
    @DisplayName("does not intercept an explicit human/advisor request")
    void ignores_escalation_request(String turn) {
        assertEquals(Optional.empty(), detector.detect(turn), "turn: " + turn);
    }

    @Test
    @DisplayName("returns empty on null input")
    void handles_null() {
        assertEquals(Optional.empty(), detector.detect(null));
    }
}
