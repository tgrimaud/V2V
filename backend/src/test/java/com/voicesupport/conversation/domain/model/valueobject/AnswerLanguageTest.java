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
}
