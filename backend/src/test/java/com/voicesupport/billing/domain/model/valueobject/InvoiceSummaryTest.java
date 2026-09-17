package com.voicesupport.billing.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.Currency;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("InvoiceSummary (available-invoice descriptor)")
class InvoiceSummaryTest {

    private static final Currency EUR = Currency.getInstance("EUR");

    @Test
    void builds_with_identity_period_and_tax_included_total() {
        // GIVEN an identity, period and TTC total
        InvoiceId id = InvoiceId.of("inv-01");
        BillingPeriod period = new BillingPeriod("inv-01", LocalDate.of(2026, 1, 15));
        Money total = Money.ofMinorUnits(4200L, EUR);

        // WHEN a summary is built
        InvoiceSummary summary = new InvoiceSummary(id, period, total);

        // THEN it exposes the tax-included total
        assertThat(summary.totalTaxIncluded().minorUnits()).isEqualTo(4200L);
    }

    @Test
    void throws_when_a_required_field_is_null() {
        // GIVEN a valid identity and period
        InvoiceId id = InvoiceId.of("inv-01");
        BillingPeriod period = new BillingPeriod("inv-01", LocalDate.of(2026, 1, 15));

        // WHEN / THEN a null total is rejected
        assertThatThrownBy(() -> new InvoiceSummary(id, period, null))
                .isInstanceOf(NullPointerException.class);
    }
}
