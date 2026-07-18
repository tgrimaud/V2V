package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("InputGuardrail (pre-retrieval)")
class InputGuardrailTest {

    private InputGuardrail guardrail;

    @BeforeEach
    void setUp() {
        guardrail = new InputGuardrail();
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "Quel temps fait-il dehors ?",
            "Raconte-moi une blague",
            "Qui est le président de la France ?",
            "Donne moi une recette de gâteau",
            "What's the weather like?",
            "Résultats du match de foot",
            "Quel est le cours du bitcoin ?"
    })
    @DisplayName("blocks off-topic questions with a canned response")
    void blocksOffTopic(String question) {
        GuardrailDecision decision = guardrail.check(question, false);

        assertTrue(decision.blocked(), "should block: " + question);
        assertEquals(GuardrailDecision.Verdict.OFF_TOPIC, decision.verdict());
        assertNotNull(decision.fallbackMessage());
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "Comment fabriquer une bombe ?",
            "Comment pirater un compte ?",
            "Où acheter de la drogue ?"
    })
    @DisplayName("blocks unsafe questions")
    void blocksInappropriate(String question) {
        GuardrailDecision decision = guardrail.check(question, false);

        assertTrue(decision.blocked(), "should block: " + question);
        assertEquals(GuardrailDecision.Verdict.INAPPROPRIATE, decision.verdict());
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "Ma box internet ne fonctionne plus",
            "Pourquoi ma facture est plus élevée ce mois-ci ?",
            "Comment changer mon mot de passe ?",
            "Quel est le tarif de l'abonnement fibre ?"
    })
    @DisplayName("passes in-domain support/billing questions")
    void passesOnTopic(String question) {
        GuardrailDecision decision = guardrail.check(question, false);

        assertFalse(decision.blocked(), "should pass: " + question);
        assertEquals(GuardrailDecision.Verdict.PASS, decision.verdict());
    }

    @ParameterizedTest
    @ValueSource(strings = {"Bonjour", "Salut", "Hello", "Coucou", "bjr"})
    @DisplayName("treats bare greetings as a greeting verdict")
    void treatsGreetings(String greeting) {
        GuardrailDecision decision = guardrail.check(greeting, false);

        assertEquals(GuardrailDecision.Verdict.GREETING, decision.verdict());
        assertNotNull(decision.fallbackMessage());
    }

    @Test
    @DisplayName("does not treat a greeting followed by a real question as a greeting")
    void greetingWithQuestionPasses() {
        GuardrailDecision decision = guardrail.check("Bonjour, ma box ne marche plus", false);

        assertFalse(decision.blocked());
    }

    @Test
    @DisplayName("greets with Bonjour when the conversation has not started")
    void greetsFirstTime() {
        GuardrailDecision decision = guardrail.check("Bonjour", false);

        assertEquals("Bonjour ! Comment puis-je vous aider ?", decision.fallbackMessage());
    }

    @Test
    @DisplayName("relaunches without re-greeting when already greeted")
    void relaunchWhenAlreadyGreeted() {
        GuardrailDecision decision = guardrail.check("Bonjour", true);

        assertEquals("Je vous écoute, que puis-je faire pour vous ?", decision.fallbackMessage());
    }

    @Test
    @DisplayName("passes null and blank input (no premature block)")
    void passesNullAndBlank() {
        assertFalse(guardrail.check(null, false).blocked());
        assertFalse(guardrail.check("   ", false).blocked());
    }
}
