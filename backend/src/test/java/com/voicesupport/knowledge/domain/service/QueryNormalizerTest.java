package com.voicesupport.knowledge.domain.service;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("QueryNormalizer (leading-greeting stripping for the embedding query, TASK-BE-029)")
class QueryNormalizerTest {

    private final QueryNormalizer normalizer = new QueryNormalizer();

    @Test
    @DisplayName("strips the BUG-003 target greeting so both sup-fr-slow variants embed the same content")
    void stripsTargetGreeting() {
        // GIVEN the greeting variant that was evicted only because of the leading "Bonjour,"
        String greeting = "Bonjour, internet est très lent chez moi.";

        // WHEN normalized
        String result = normalizer.normalize(greeting);

        // THEN the leading greeting is gone and the rest is preserved verbatim (accents kept)
        assertEquals("internet est très lent chez moi.", result);
        assertTrue(normalizer.rewrites(greeting));
    }

    @ParameterizedTest
    @CsvSource(delimiter = '|', value = {
            "Bonjour, ma facture a augmenté | ma facture a augmenté",
            "Salut ma box ne marche plus | ma box ne marche plus",
            "Hello, why is my bill higher | why is my bill higher",
            "Hi my internet is slow | my internet is slow",
            "Bonsoir : je veux résilier | je veux résilier",
            "Coucou !! internet lent | internet lent",
            "bjr ma connexion coupe | ma connexion coupe",
            "Good morning, my box is broken | my box is broken",
            "Bonjour, salut, ma facture | ma facture"
    })
    @DisplayName("strips leading FR/EN greetings (with varied separators, casing and stacked greetings)")
    void stripsVariousGreetings(String input, String expected) {
        assertEquals(expected, normalizer.normalize(input));
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "Ma connexion internet est très lente.",
            "Pourquoi ma facture a-t-elle augmenté ?",
            "Why is my internet not working"
    })
    @DisplayName("leaves a greeting-free question unchanged and reports no rewrite")
    void leavesPlainQuestionUnchanged(String question) {
        assertEquals(question, normalizer.normalize(question));
        assertFalse(normalizer.rewrites(question));
    }

    @ParameterizedTest
    @ValueSource(strings = {"salutations", "history of my account", "hip problem", "yoga class"})
    @DisplayName("does not strip a greeting substring embedded in a longer word")
    void doesNotStripGreetingInsideWord(String question) {
        assertEquals(question, normalizer.normalize(question));
        assertFalse(normalizer.rewrites(question));
    }

    @ParameterizedTest
    @ValueSource(strings = {"Bonjour", "Bonjour.", "Salut !", "Hello", "bjr"})
    @DisplayName("returns the original when stripping would empty the query (whole-utterance greeting)")
    void keepsWholeUtteranceGreeting(String greeting) {
        // Whole-utterance greetings are already blocked by the input guardrail before retrieval;
        // defensively the normalizer never returns a blank query.
        assertEquals(greeting, normalizer.normalize(greeting));
        assertFalse(normalizer.rewrites(greeting));
    }

    @Test
    @DisplayName("null and blank inputs pass through untouched")
    void handlesNullAndBlank() {
        assertEquals(null, normalizer.normalize(null));
        assertEquals("   ", normalizer.normalize("   "));
        assertFalse(normalizer.rewrites(null));
        assertFalse(normalizer.rewrites("   "));
    }
}
