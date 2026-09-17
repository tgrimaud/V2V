package com.voicesupport.billing.domain.service;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("BillingIntentDetector (deterministic FR/EN intent guard)")
class BillingIntentDetectorTest {

    private final BillingIntentDetector detector = new BillingIntentDetector(
            List.of("facture", "prelevement", "invoice", "bill"));

    @Test
    void detects_a_french_billing_question_ignoring_accents_and_case() {
        // GIVEN a French billing question with an accent and mixed case
        // WHEN the detector inspects it
        boolean billing = detector.isBillingExplanationRequest("Pourquoi ma FACTURE a augmenté ?");

        // THEN it is recognized as a billing request (accent/case folded)
        assertThat(billing).isTrue();
    }

    @Test
    void detects_a_french_keyword_written_without_its_accent() {
        // GIVEN "prélèvement" written unaccented, matching the folded keyword "prelevement"
        // WHEN / THEN it is still recognized
        assertThat(detector.isBillingExplanationRequest("Je vois un prelevement bizarre")).isTrue();
        assertThat(detector.isBillingExplanationRequest("Je vois un prélèvement bizarre")).isTrue();
    }

    @Test
    void detects_an_english_billing_question() {
        // GIVEN an English billing question
        // WHEN / THEN it is recognized
        assertThat(detector.isBillingExplanationRequest("Why did my bill go up this month?")).isTrue();
    }

    @Test
    void ignores_a_non_billing_question() {
        // GIVEN a question with no billing keyword
        // WHEN / THEN it is not a billing request
        assertThat(detector.isBillingExplanationRequest("Comment configurer mon routeur ?")).isFalse();
    }

    @Test
    void does_not_match_a_keyword_embedded_in_another_word() {
        // GIVEN a word that merely contains a keyword substring ("billed" contains "bill" but "billy"
        // is a different word) — word-boundary matching must not false-positive on "billboard"
        // WHEN / THEN the substring inside an unrelated word does not trigger detection
        assertThat(detector.isBillingExplanationRequest("I saw a billboard on the road")).isFalse();
    }

    @Test
    void returns_false_for_null_or_blank() {
        // GIVEN / WHEN / THEN null and blank transcripts are never billing requests
        assertThat(detector.isBillingExplanationRequest(null)).isFalse();
        assertThat(detector.isBillingExplanationRequest("   ")).isFalse();
    }
}
