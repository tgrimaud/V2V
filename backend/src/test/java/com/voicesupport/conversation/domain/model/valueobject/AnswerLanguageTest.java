package com.voicesupport.conversation.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("AnswerLanguage (FR/EN detection, directive, config parsing)")
class AnswerLanguageTest {

    @Test
    @DisplayName("an English question is detected as English")
    void detectsEnglish() {
        // WHEN detecting a clearly English question
        Optional<AnswerLanguage> detected = AnswerLanguage.detect("Why does my internet connection not work?");

        // THEN English is returned
        assertEquals(Optional.of(AnswerLanguage.ENGLISH), detected);
    }

    @Test
    @DisplayName("a French question is detected as French")
    void detectsFrench() {
        // WHEN detecting a clearly French question
        Optional<AnswerLanguage> detected = AnswerLanguage.detect("Pourquoi ma facture augmente ce mois-ci ?");

        // THEN French is returned
        assertEquals(Optional.of(AnswerLanguage.FRENCH), detected);
    }

    @Test
    @DisplayName("an ambiguous or empty turn yields no detection")
    void ambiguousYieldsEmpty() {
        // WHEN the text carries no language signal
        assertTrue(AnswerLanguage.detect("42").isEmpty());
        assertTrue(AnswerLanguage.detect("   ").isEmpty());
        assertTrue(AnswerLanguage.detect(null).isEmpty());
    }

    @Test
    @DisplayName("a language code is parsed, defaulting to English for unknown values")
    void parsesCode() {
        assertEquals(AnswerLanguage.FRENCH, AnswerLanguage.fromCode("fr"));
        assertEquals(AnswerLanguage.ENGLISH, AnswerLanguage.fromCode("EN"));
        assertEquals(AnswerLanguage.ENGLISH, AnswerLanguage.fromCode("de"));
        assertEquals(AnswerLanguage.ENGLISH, AnswerLanguage.fromCode(null));
    }

    @Test
    @DisplayName("each language exposes a forceful directive and its own hand-off marker")
    void directiveAndMarkers() {
        assertTrue(AnswerLanguage.ENGLISH.llmDirective().contains("ONLY in English"));
        assertTrue(AnswerLanguage.FRENCH.llmDirective().contains("UNIQUEMENT en français"));
        assertTrue(AnswerLanguage.ENGLISH.handoffMarkers().contains("transfer you to an advisor"));
        assertTrue(AnswerLanguage.FRENCH.handoffMarkers().contains("transfère à un conseiller"));
    }

    @Test
    @DisplayName("the directive restricts the hand-off to empty/unrelated context (BUG-004)")
    void directiveConditionsTheHandoff() {
        // GIVEN the wording directive that the LLM receives per turn
        String french = AnswerLanguage.FRENCH.llmDirective();
        String english = AnswerLanguage.ENGLISH.llmDirective();

        // THEN it still carries the exact hand-off sentence the OutputGuardrail matches
        assertTrue(french.contains("je vous transfère à un conseiller."));
        assertTrue(english.contains("I'll transfer you to an advisor."));
        // AND it tells the model to use partial context and only refuse when context is unusable,
        // so a grounded turn is not converted into a spurious refusal (BUG-004).
        assertTrue(french.contains("QUE si"));
        assertTrue(french.contains("partiellement"));
        assertTrue(english.contains("ONLY if"));
        assertTrue(english.contains("partially"));
    }
}
