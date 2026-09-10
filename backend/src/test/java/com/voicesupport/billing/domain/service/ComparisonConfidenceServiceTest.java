package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.ExplanationConfidence;
import com.voicesupport.billing.domain.model.ExplanationReadiness;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceComparison;
import com.voicesupport.billing.domain.model.InvoiceGroup;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.InvoiceSection;
import com.voicesupport.billing.domain.model.ReadinessReason;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingPeriod;
import com.voicesupport.billing.domain.model.valueobject.Evidence;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceLevel;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;
import com.voicesupport.billing.domain.model.valueobject.Money;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.Currency;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("ComparisonConfidenceService (evidence-sufficiency gate)")
class ComparisonConfidenceServiceTest {

    private static final Currency EUR = Currency.getInstance("EUR");
    private final InvoiceComparisonService comparisonService = new InvoiceComparisonService();
    private final ComparisonConfidenceService gate = new ComparisonConfidenceService(0.05);

    @Test
    void a_fully_reconciled_comparison_is_explainable_without_escalation() {
        // GIVEN the discount-expiry journey, whose +500 change is fully attributed (zero residual)
        InvoiceComparison comparison =
                comparisonService.compare(fixture("eir-002", "2026-01"), fixture("eir-002", "2026-02"));

        // WHEN the gate assesses it
        ExplanationReadiness readiness = gate.assess(comparison);

        // THEN it is EXPLAINABLE, no escalation, residual zero
        assertThat(readiness.confidence()).isEqualTo(ExplanationConfidence.EXPLAINABLE);
        assertThat(readiness.reason()).isEqualTo(ReadinessReason.FULLY_EXPLAINED);
        assertThat(readiness.escalate()).isFalse();
        assertThat(readiness.unexplainedAmount().isZero()).isTrue();
    }

    @Test
    void two_invoices_without_billed_lines_are_insufficient_and_escalate() {
        // GIVEN the unusable journey (eir-006): both invoices present but with no billed line
        InvoiceComparison comparison =
                comparisonService.compare(fixture("eir-006", "2026-01"), fixture("eir-006", "2026-02"));

        // WHEN the gate assesses it (this is why the gate needs the invoices, not just the deltas:
        // an unusable invoice otherwise looks like a no-change)
        ExplanationReadiness readiness = gate.assess(comparison);

        // THEN it is INSUFFICIENT with NO_USABLE_LINES and escalates
        assertThat(readiness.confidence()).isEqualTo(ExplanationConfidence.INSUFFICIENT);
        assertThat(readiness.reason()).isEqualTo(ReadinessReason.NO_USABLE_LINES);
        assertThat(readiness.escalate()).isTrue();
    }

    @Test
    void a_small_residual_within_tolerance_is_partial_without_escalation() {
        // GIVEN a +10000 total with a single +9600 line -> 400 residual (4% <= 5% tolerance)
        InvoiceComparison comparison = comparisonService.compare(
                header("prev", 0L, List.of()),
                header("curr", 10000L, List.of(line("misc", LineCategory.OTHER, 9600L))));

        // WHEN the gate assesses it
        ExplanationReadiness readiness = gate.assess(comparison);

        // THEN it is PARTIAL (phrase with a caveat), no escalation, residual surfaced
        assertThat(readiness.confidence()).isEqualTo(ExplanationConfidence.PARTIAL);
        assertThat(readiness.reason()).isEqualTo(ReadinessReason.PARTIAL_RESIDUAL);
        assertThat(readiness.escalate()).isFalse();
        assertThat(readiness.unexplainedAmount().minorUnits()).isEqualTo(400L);
    }

    @Test
    void a_residual_above_tolerance_is_insufficient_and_escalates() {
        // GIVEN a +1000 total with only an +800 line -> 200 residual (20% > 5% tolerance)
        InvoiceComparison comparison = comparisonService.compare(
                header("prev", 0L, List.of()),
                header("curr", 1000L, List.of(line("misc", LineCategory.OTHER, 800L))));

        // WHEN the gate assesses it
        ExplanationReadiness readiness = gate.assess(comparison);

        // THEN it is INSUFFICIENT with RESIDUAL_TOO_HIGH and escalates
        assertThat(readiness.confidence()).isEqualTo(ExplanationConfidence.INSUFFICIENT);
        assertThat(readiness.reason()).isEqualTo(ReadinessReason.RESIDUAL_TOO_HIGH);
        assertThat(readiness.escalate()).isTrue();
        assertThat(readiness.unexplainedAmount().minorUnits()).isEqualTo(200L);
    }

    @Test
    void rejects_a_negative_tolerance() {
        // GIVEN / WHEN / THEN a negative ratio is rejected at construction
        assertThatThrownBy(() -> new ComparisonConfidenceService(-0.1))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejects_a_null_comparison() {
        // GIVEN / WHEN / THEN a null comparison is rejected
        assertThatThrownBy(() -> gate.assess(null)).isInstanceOf(NullPointerException.class);
    }

    private static Invoice fixture(String account, String periodSuffix) {
        return BssBillingFixtures.all().get(AccountId.of(account)).stream()
                .filter(invoice -> invoice.period().id().endsWith(periodSuffix))
                .findFirst().orElseThrow();
    }

    private static Invoice header(String id, long totalTaxIncludedCents, List<InvoiceItem> items) {
        InvoiceGroup group = new InvoiceGroup(id + "-g", "Charges", null, 0, amounts(0L), items);
        InvoiceSection section = new InvoiceSection(id + "-s", "Invoice", 0, true, amounts(0L), List.of(group));
        return new Invoice(InvoiceId.of(id), AccountId.of("eir-x"), InvoiceLevel.BILLING_ACCOUNT,
                new BillingPeriod(id, LocalDate.of(2026, 2, 15)), amounts(totalTaxIncludedCents),
                List.of(section));
    }

    private static InvoiceItem line(String id, LineCategory category, long taxIncludedCents) {
        return new InvoiceItem(id, category.name(), id, "S", category, amounts(taxIncludedCents),
                new Evidence("test", null, id));
    }

    private static LineAmounts amounts(long taxIncludedCents) {
        long tax = taxIncludedCents / 6L;
        long taxExcluded = taxIncludedCents - tax;
        return new LineAmounts(cents(taxIncludedCents), cents(taxExcluded), cents(tax));
    }

    private static Money cents(long value) {
        return Money.ofMinorUnits(value, EUR);
    }
}
