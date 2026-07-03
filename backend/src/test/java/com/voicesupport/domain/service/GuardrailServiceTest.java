package com.voicesupport.domain.service;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.GuardrailResult;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class GuardrailServiceTest {

    private GuardrailService service;

    @BeforeEach
    void setUp() {
        service = new GuardrailService(0.65);
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "Quel temps fait-il dehors ?",
            "Raconte-moi une blague",
            "Qui est le président de la France ?",
            "Donne moi une recette de gâteau",
            "What's the weather like?",
            "Tell me a joke",
            "Résultats du match de foot",
            "Quel est la météo de demain ?",
            "Quelle est la météo demain ?",
            "Donne-moi la météo",
            "C'est quoi le weather forecast ?",
            "Qui a inventé la machine à vapeur ?",
            "Traduis-moi ce texte en anglais",
            "Quel est le cours du bitcoin ?"
    })
    void check_before_search_blocks_off_topic_questions(String question) {
        // WHEN
        GuardrailResult result = service.checkBeforeSearch(question);

        // THEN
        assertTrue(result.blocked(), "Should block: " + question);
        assertEquals(GuardrailResult.Verdict.OFF_TOPIC, result.verdict());
        assertNotNull(result.fallbackMessage());
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "Ma box internet ne fonctionne plus",
            "Comment changer mon mot de passe ?",
            "Je n'arrive pas à me connecter",
            "Quel est le tarif de l'abonnement fibre ?",
            "How do I reset my password?",
            "I can't access my account",
            "Mon code wifi ne marche pas",
            "Quel est le numéro de série de ma box ?",
            "Mon streaming est lent depuis hier",
            "Le code PIN de ma carte SIM est bloqué",
            "Je voudrais changer mon code d'accès"
    })
    void check_before_search_passes_on_topic_questions(String question) {
        // WHEN
        GuardrailResult result = service.checkBeforeSearch(question);

        // THEN
        assertFalse(result.blocked(), "Should pass: " + question);
        assertEquals(GuardrailResult.Verdict.PASS, result.verdict());
    }

    @Test
    void check_before_search_passes_very_short_questions() {
        // WHEN
        GuardrailResult result = service.checkBeforeSearch("ok");

        // THEN
        assertFalse(result.blocked());
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "Bonjour",
            "bonjour",
            "Salut",
            "Hello",
            "Hi",
            "Coucou",
            "Hey",
            "Bonsoir",
            "Comment ça va ?",
            "How are you?",
            "bjr",
            "slt",
            "cc",
            "bsr",
            "ça va ?"
    })
    void check_before_search_treats_greetings_as_greeting_verdict(String greeting) {
        // WHEN
        GuardrailResult result = service.checkBeforeSearch(greeting);

        // THEN
        assertTrue(result.blocked());
        assertEquals(GuardrailResult.Verdict.GREETING, result.verdict());
        assertNotNull(result.fallbackMessage());
    }

    @Test
    void check_before_search_does_not_treat_greeting_with_question_as_greeting() {
        // WHEN
        GuardrailResult result = service.checkBeforeSearch("Bonjour, ma box ne marche plus");

        // THEN
        assertFalse(result.blocked());
        assertEquals(GuardrailResult.Verdict.PASS, result.verdict());
    }

    @Test
    void check_before_search_greets_with_bonjour_when_conversation_not_yet_started() {
        // WHEN
        GuardrailResult result = service.checkBeforeSearch("Bonjour", false);

        // THEN
        assertEquals(GuardrailResult.Verdict.GREETING, result.verdict());
        assertEquals("Bonjour ! Comment puis-je vous aider ?", result.fallbackMessage());
    }

    @Test
    void check_before_search_relaunches_without_re_greeting_when_already_greeted() {
        // WHEN
        GuardrailResult result = service.checkBeforeSearch("Bonjour", true);

        // THEN
        assertEquals(GuardrailResult.Verdict.GREETING, result.verdict());
        assertEquals("Je vous écoute, que puis-je faire pour vous ?", result.fallbackMessage());
    }

    @Test
    void check_before_search_relaunches_in_english_when_already_greeted() {
        // WHEN
        GuardrailResult result = service.checkBeforeSearch("How are you?", true);

        // THEN
        assertEquals(GuardrailResult.Verdict.GREETING, result.verdict());
        assertEquals("I'm listening, how can I help you?", result.fallbackMessage());
    }

    @Test
    void check_before_search_passes_null_question() {
        // WHEN
        GuardrailResult result = service.checkBeforeSearch(null);

        // THEN
        assertFalse(result.blocked());
    }

    @Test
    void check_after_search_blocks_when_no_citations_found() {
        // WHEN
        GuardrailResult result = service.checkAfterSearch(
                "Ma question ici", List.of());

        // THEN
        assertTrue(result.blocked());
        assertEquals(GuardrailResult.Verdict.LOW_CONFIDENCE, result.verdict());
        assertTrue(result.fallbackMessage().contains("informations fiables"));
    }

    @Test
    void check_after_search_blocks_when_best_score_below_threshold() {
        // GIVEN
        List<Citation> lowScoreCitations = List.of(
                new Citation("source.md", "Section", "Some text", 0.55),
                new Citation("other.md", "Other", "More text", 0.40)
        );

        // WHEN
        GuardrailResult result = service.checkAfterSearch(
                "Ma question ici", lowScoreCitations);

        // THEN
        assertTrue(result.blocked());
        assertEquals(GuardrailResult.Verdict.LOW_CONFIDENCE, result.verdict());
    }

    @Test
    void check_after_search_passes_when_best_score_above_threshold() {
        // GIVEN
        List<Citation> goodCitations = List.of(
                new Citation("faq.md", "Internet", "Redémarrez la box", 0.85),
                new Citation("guide.md", "Dépannage", "Vérifiez les câbles", 0.72)
        );

        // WHEN
        GuardrailResult result = service.checkAfterSearch(
                "Ma box ne marche pas", goodCitations);

        // THEN
        assertFalse(result.blocked());
        assertEquals(GuardrailResult.Verdict.PASS, result.verdict());
    }

    @Test
    void check_after_search_returns_english_message_for_english_question() {
        // WHEN
        GuardrailResult result = service.checkAfterSearch(
                "How do I fix this? (Please answer in English.)", List.of());

        // THEN
        assertTrue(result.blocked());
        assertTrue(result.fallbackMessage().contains("reliable information"));
    }

    @Test
    void check_after_search_returns_french_message_for_french_question() {
        // WHEN
        GuardrailResult result = service.checkAfterSearch(
                "Comment réparer ma connexion ?", List.of());

        // THEN
        assertTrue(result.blocked());
        assertTrue(result.fallbackMessage().contains("informations fiables"));
    }

    @Test
    void check_after_search_applies_custom_confidence_threshold() {
        // GIVEN
        GuardrailService strictService = new GuardrailService(0.90);
        List<Citation> citations = List.of(
                new Citation("faq.md", "Section", "Text", 0.85)
        );

        // WHEN
        GuardrailResult result = strictService.checkAfterSearch("Question", citations);

        // THEN
        assertTrue(result.blocked());
        assertEquals(GuardrailResult.Verdict.LOW_CONFIDENCE, result.verdict());
    }
}
