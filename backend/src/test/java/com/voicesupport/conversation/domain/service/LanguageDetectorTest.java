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

    @Test
    @DisplayName("exposes the configured default language")
    void exposesConfiguredDefault() {
        // GIVEN detectors configured with explicit default languages
        // WHEN the configured default is read back (for prompt/telemetry wiring)
        // THEN each detector returns its configured default (pins the getter against a null return)
        assertEquals(AnswerLanguage.FRENCH, new LanguageDetector(AnswerLanguage.FRENCH).defaultLanguage());
        assertEquals(AnswerLanguage.ENGLISH, detector.defaultLanguage());
    }

    @Test
    @DisplayName("stickiness scans back to the OLDEST history turn when only it carries a language")
    void stickinessReachesOldestTurn() {
        // GIVEN only the oldest turn (index 0) is detectable; the newer turns are ambiguous
        List<String> history = List.of("Pourquoi ma facture augmente ?", "123", "456");

        // WHEN the current turn is ambiguous
        AnswerLanguage resolved = detector.resolve("42", history);

        // THEN the scan must reach index 0 to find French; a loop that stops at i > 0 would miss it
        // and fall back to the English default (pins the `i >= 0` lower bound).
        assertEquals(AnswerLanguage.FRENCH, resolved);
    }

    @Test
    @DisplayName("a forced UI language overrides detection and stickiness (US-042 BR1/BR2)")
    void forcedLanguageWins() {
        // GIVEN a clearly French question and a French session history
        List<String> frenchHistory = List.of("Client : Pourquoi ma facture augmente ?");

        // WHEN English is forced by the UI selector
        AnswerLanguage resolved = detector.resolve("Pourquoi ma facture augmente ?", frenchHistory, "en");

        // THEN the forced language wins over the detected/sticky French
        assertEquals(AnswerLanguage.ENGLISH, resolved);
        // AND forcing French wins over a clearly English question
        assertEquals(AnswerLanguage.FRENCH,
                detector.resolve("Why is my bill higher this month?", List.of(), "fr"));
    }

    @Test
    @DisplayName("a blank/null forced language falls back to normal detection (US-042 BR3)")
    void blankForcedLanguageFallsBackToDetection() {
        // WHEN the forced code is null or blank the per-turn decision is unchanged
        assertEquals(AnswerLanguage.FRENCH, detector.resolve("Pourquoi ma facture augmente ?", List.of(), null));
        assertEquals(AnswerLanguage.ENGLISH, detector.resolve("Why is my bill higher?", List.of(), "  "));
    }
}
