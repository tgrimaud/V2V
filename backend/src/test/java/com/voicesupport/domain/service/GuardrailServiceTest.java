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
            "Résultats du match de foot"
    })
    void shouldBlockOffTopicQuestions(String question) {
        GuardrailResult result = service.checkBeforeSearch(question);

        assertTrue(result.blocked());
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
            "I can't access my account"
    })
    void shouldPassOnTopicQuestions(String question) {
        GuardrailResult result = service.checkBeforeSearch(question);

        assertFalse(result.blocked());
        assertEquals(GuardrailResult.Verdict.PASS, result.verdict());
    }

    @Test
    void shouldPassVeryShortQuestions() {
        GuardrailResult result = service.checkBeforeSearch("ok");

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
            "How are you?"
    })
    void shouldRespondToGreetingsWithoutRAG(String greeting) {
        GuardrailResult result = service.checkBeforeSearch(greeting);

        assertTrue(result.blocked());
        assertEquals(GuardrailResult.Verdict.GREETING, result.verdict());
        assertNotNull(result.fallbackMessage());
    }

    @Test
    void shouldNotTreatGreetingWithQuestionAsGreeting() {
        GuardrailResult result = service.checkBeforeSearch("Bonjour, ma box ne marche plus");

        assertFalse(result.blocked());
        assertEquals(GuardrailResult.Verdict.PASS, result.verdict());
    }

    @Test
    void shouldPassNullQuestion() {
        GuardrailResult result = service.checkBeforeSearch(null);

        assertFalse(result.blocked());
    }

    @Test
    void shouldBlockWhenNoCitationsFound() {
        GuardrailResult result = service.checkAfterSearch(
                "Ma question ici", List.of());

        assertTrue(result.blocked());
        assertEquals(GuardrailResult.Verdict.LOW_CONFIDENCE, result.verdict());
        assertTrue(result.fallbackMessage().contains("informations fiables"));
    }

    @Test
    void shouldBlockWhenBestScoreBelowThreshold() {
        List<Citation> lowScoreCitations = List.of(
                new Citation("source.md", "Section", "Some text", 0.55),
                new Citation("other.md", "Other", "More text", 0.40)
        );

        GuardrailResult result = service.checkAfterSearch(
                "Ma question ici", lowScoreCitations);

        assertTrue(result.blocked());
        assertEquals(GuardrailResult.Verdict.LOW_CONFIDENCE, result.verdict());
    }

    @Test
    void shouldPassWhenBestScoreAboveThreshold() {
        List<Citation> goodCitations = List.of(
                new Citation("faq.md", "Internet", "Redémarrez la box", 0.85),
                new Citation("guide.md", "Dépannage", "Vérifiez les câbles", 0.72)
        );

        GuardrailResult result = service.checkAfterSearch(
                "Ma box ne marche pas", goodCitations);

        assertFalse(result.blocked());
        assertEquals(GuardrailResult.Verdict.PASS, result.verdict());
    }

    @Test
    void shouldReturnEnglishMessageForEnglishQuestion() {
        GuardrailResult result = service.checkAfterSearch(
                "How do I fix this? (Please answer in English.)", List.of());

        assertTrue(result.blocked());
        assertTrue(result.fallbackMessage().contains("reliable information"));
    }

    @Test
    void shouldReturnFrenchMessageForFrenchQuestion() {
        GuardrailResult result = service.checkAfterSearch(
                "Comment réparer ma connexion ?", List.of());

        assertTrue(result.blocked());
        assertTrue(result.fallbackMessage().contains("informations fiables"));
    }

    @Test
    void shouldUseCustomThreshold() {
        GuardrailService strictService = new GuardrailService(0.90);

        List<Citation> citations = List.of(
                new Citation("faq.md", "Section", "Text", 0.85)
        );

        GuardrailResult result = strictService.checkAfterSearch("Question", citations);

        assertTrue(result.blocked());
        assertEquals(GuardrailResult.Verdict.LOW_CONFIDENCE, result.verdict());
    }
}
