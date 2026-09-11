package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.ExplanationReadiness;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceComparison;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("BillingExplanationComposer (grounded, language-aware text)")
class BillingExplanationComposerTest {

    private final InvoiceComparisonService comparisonService = new InvoiceComparisonService();
    private final ComparisonConfidenceService gate = new ComparisonConfidenceService(0.05);
    private final BillingExplanationComposer composer = new BillingExplanationComposer();

    @Test
    void composes_a_french_explanation_carrying_every_grounded_amount() {
        // GIVEN the discount-expiry journey (+500 cents = 5.00 €), fully reconciled
        InvoiceComparison comparison =
                comparisonService.compare(fixture("eir-002", "2026-01"), fixture("eir-002", "2026-02"));
        ExplanationReadiness readiness = gate.assess(comparison);

        // WHEN it is composed in French
        String text = composer.compose(comparison, readiness, "fr");

        // THEN the amount is present (so the OutputGuardrail passes) and the cause is named in French
        assertThat(text).contains("5.00 €");
        assertThat(text).contains("augmenté");
        assertThat(text).contains("remise");
    }

    @Test
    void composes_an_english_explanation_for_the_same_comparison() {
        // GIVEN the same discount-expiry comparison
        InvoiceComparison comparison =
                comparisonService.compare(fixture("eir-002", "2026-01"), fixture("eir-002", "2026-02"));
        ExplanationReadiness readiness = gate.assess(comparison);

        // WHEN composed in English
        String text = composer.compose(comparison, readiness, "en");

        // THEN it carries the amount and English wording
        assertThat(text).contains("5.00 €");
        assertThat(text).contains("increased");
        assertThat(text).contains("discount");
    }

    @Test
    void describes_an_identical_invoice_as_unchanged() {
        // GIVEN the nominal journey (identical invoices, zero delta)
        InvoiceComparison comparison =
                comparisonService.compare(fixture("eir-001", "2026-01"), fixture("eir-001", "2026-02"));
        ExplanationReadiness readiness = gate.assess(comparison);

        // WHEN composed
        String textFr = composer.compose(comparison, readiness, "fr");
        String textEn = composer.compose(comparison, readiness, "en");

        // THEN it states the bill is unchanged, in each language
        assertThat(textFr).contains("identique");
        assertThat(textEn).contains("unchanged");
    }

    @Test
    void operational_messages_are_language_aware() {
        // GIVEN / WHEN / THEN the safe operational/hand-off messages are localized
        assertThat(composer.askReference("fr")).contains("référence");
        assertThat(composer.askReference("en")).contains("reference");
        assertThat(composer.cannotVerify("fr")).contains("conseiller");
        assertThat(composer.cannotVerify("en")).contains("advisor");
        assertThat(composer.notEnoughData("fr")).contains("conseiller");
        assertThat(composer.notABillingRequest("en")).contains("bill");
    }

    private static Invoice fixture(String account, String periodSuffix) {
        return BssBillingFixtures.all().get(AccountId.of(account)).stream()
                .filter(invoice -> invoice.period().id().endsWith(periodSuffix))
                .findFirst().orElseThrow();
    }
}
