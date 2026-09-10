package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.BillingCauseType;
import com.voicesupport.billing.domain.model.ChangeKind;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceComparison;
import com.voicesupport.billing.domain.model.InvoiceGroup;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.InvoiceSection;
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

@DisplayName("InvoiceComparisonService (deterministic comparison)")
class InvoiceComparisonServiceTest {

    private static final Currency EUR = Currency.getInstance("EUR");
    private final InvoiceComparisonService service = new InvoiceComparisonService();

    @Test
    void identical_invoices_produce_no_delta_no_cause() {
        // GIVEN the nominal journey (eir-001): two identical invoices
        Invoice previous = fixture("eir-001", "2026-01");
        Invoice current = fixture("eir-001", "2026-02");

        // WHEN they are compared
        InvoiceComparison comparison = service.compare(previous, current);

        // THEN there is no change, no line delta, no cause and no residual
        assertThat(comparison.totalDelta().isZero()).isTrue();
        assertThat(comparison.lineDeltas()).isEmpty();
        assertThat(comparison.causes()).isEmpty();
        assertThat(comparison.unexplainedAmount().isZero()).isTrue();
    }

    @Test
    void an_expired_discount_is_attributed_to_discount_expiry() {
        // GIVEN the discount-expiry journey (eir-002): previous had a -500 discount, current does not
        InvoiceComparison comparison =
                service.compare(fixture("eir-002", "2026-01"), fixture("eir-002", "2026-02"));

        // WHEN / THEN the +500 change is attributed to a single DISCOUNT_EXPIRY cause, fully explained
        assertThat(comparison.totalDelta().minorUnits()).isEqualTo(500L);
        assertThat(comparison.lineDeltas()).singleElement().satisfies(delta -> {
            assertThat(delta.kind()).isEqualTo(ChangeKind.DISAPPEARED);
            assertThat(delta.contribution().minorUnits()).isEqualTo(500L);
        });
        assertThat(comparison.causes()).singleElement().satisfies(cause -> {
            assertThat(cause.type()).isEqualTo(BillingCauseType.DISCOUNT_EXPIRY);
            assertThat(cause.impact().minorUnits()).isEqualTo(500L);
        });
        assertThat(comparison.unexplainedAmount().isZero()).isTrue();
    }

    @Test
    void a_new_overage_line_is_attributed_to_usage_overage() {
        // GIVEN the overage journey (eir-003): current adds a +1200 overage line
        InvoiceComparison comparison =
                service.compare(fixture("eir-003", "2026-01"), fixture("eir-003", "2026-02"));

        // WHEN / THEN the +1200 change is an APPEARED line attributed to USAGE_OVERAGE
        assertThat(comparison.totalDelta().minorUnits()).isEqualTo(1200L);
        assertThat(comparison.lineDeltas()).singleElement().satisfies(delta ->
                assertThat(delta.kind()).isEqualTo(ChangeKind.APPEARED));
        assertThat(comparison.causes()).singleElement().satisfies(cause ->
                assertThat(cause.type()).isEqualTo(BillingCauseType.USAGE_OVERAGE));
        assertThat(comparison.unexplainedAmount().isZero()).isTrue();
    }

    @Test
    void a_prorated_option_is_attributed_to_proration() {
        // GIVEN the proration journey (eir-004): current adds a +800 prorated option
        InvoiceComparison comparison =
                service.compare(fixture("eir-004", "2026-01"), fixture("eir-004", "2026-02"));

        // WHEN / THEN the +800 change is attributed to PRORATION
        assertThat(comparison.totalDelta().minorUnits()).isEqualTo(800L);
        assertThat(comparison.causes()).singleElement().satisfies(cause ->
                assertThat(cause.type()).isEqualTo(BillingCauseType.PRORATION));
        assertThat(comparison.unexplainedAmount().isZero()).isTrue();
    }

    @Test
    void surfaces_the_residual_when_line_deltas_do_not_reconcile_with_the_total() {
        // GIVEN a header total that changed by 1000 but only an 800 line (of an unmapped category)
        Invoice previous = header("prev", 0L, List.of());
        Invoice current = header("curr", 1000L, List.of(line("misc", LineCategory.OTHER, 800L)));

        // WHEN they are compared
        InvoiceComparison comparison = service.compare(previous, current);

        // THEN the 800 goes to an UNEXPLAINED cause and the 200 header/line gap is the residual
        assertThat(comparison.totalDelta().minorUnits()).isEqualTo(1000L);
        assertThat(comparison.causes()).singleElement().satisfies(cause -> {
            assertThat(cause.type()).isEqualTo(BillingCauseType.UNEXPLAINED);
            assertThat(cause.impact().minorUnits()).isEqualTo(800L);
        });
        assertThat(comparison.unexplainedAmount().minorUnits()).isEqualTo(200L);
    }

    @Test
    void throws_when_an_invoice_is_null() {
        // GIVEN a valid current invoice
        Invoice current = fixture("eir-001", "2026-02");

        // WHEN / THEN a null previous invoice is rejected
        assertThatThrownBy(() -> service.compare(null, current))
                .isInstanceOf(NullPointerException.class);
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
