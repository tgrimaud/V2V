package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DisplayName("LanguageDetector (per-turn language: question -> stickiness -> default)")
class LanguageDetectorTest {

    private final LanguageDetector detector = new LanguageDetector(AnswerLanguage.ENGLISH);

    @Test
    @DisplayName("the question language wins when it is clear (BR1)")
    void resolvesFromQuestion() {
        // WHEN the question is clearly English / French
        assertEquals(AnswerLanguage.ENGLISH, detector.resolve("Why is my bill higher this month?", List.of()));
        assertEquals(AnswerLanguage.FRENCH, detector.resolve("Pourquoi ma facture augmente ?", List.of()));
    }

    @Test
    @DisplayName("an ambiguous turn falls back to the configured default (BR2)")
    void resolvesToDefaultWhenAmbiguous() {
        // GIVEN detectors with different defaults
        LanguageDetector french = new LanguageDetector(AnswerLanguage.FRENCH);

        // WHEN the turn is too ambiguous to detect and no session language exists
        assertEquals(AnswerLanguage.ENGLISH, detector.resolve("42", List.of()));
        assertEquals(AnswerLanguage.FRENCH, french.resolve("42", List.of()));
    }

    @Test
    @DisplayName("an ambiguous turn keeps the current conversation language (BR3 stickiness)")
    void resolvesFromHistoryWhenAmbiguous() {
        // GIVEN a prior French turn in the history
        List<String> history = List.of(
                "Client : Pourquoi ma facture augmente ?", "Assistant : Réponse.");

        // WHEN the current turn is ambiguous, the default is English but the session is French
        AnswerLanguage resolved = detector.resolve("42", history);

        // THEN stickiness keeps French rather than jumping to the English default
        assertEquals(AnswerLanguage.FRENCH, resolved);
    }

    @Test
    @DisplayName("an ambiguous turn with an ambiguous history falls back to the default")
    void resolvesToDefaultWhenHistoryAmbiguous() {
        // GIVEN no usable language signal anywhere
        AnswerLanguage resolved = detector.resolve("42", List.of("123", "456"));

        // THEN the configured default is used
        assertEquals(AnswerLanguage.ENGLISH, resolved);
    }

    @Test
    @DisplayName("a null default falls back to English")
    void nullDefaultIsEnglish() {
        LanguageDetector nullDefault = new LanguageDetector(null);
        assertEquals(AnswerLanguage.ENGLISH, nullDefault.resolve("42", List.of()));
    }
}
