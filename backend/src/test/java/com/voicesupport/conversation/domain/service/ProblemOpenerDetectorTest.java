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
            // A concrete question marker (interrogative or number) makes the turn specific enough to
            // retrieve — the detector must NOT flag it as a generic opener.
            "Pourquoi ai-je un problème de facturation ?",
            "J'ai un problème : ma facture a augmenté de 10 euros",
            "How do I fix the problem with my bill?",
            "Combien coûte le forfait fibre ?"})
    @DisplayName("does not flag a specific question (question marker / number present)")
    void ignores_specific_question(String question) {
        assertEquals(Optional.empty(), detector.detect(question), "question: " + question);
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

    @Test
    @DisplayName("returns empty on null input")
    void handles_null() {
        assertEquals(Optional.empty(), detector.detect(null));
    }
}
