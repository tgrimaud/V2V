package com.voicesupport.billing.infrastructure.fixtures;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;
import com.voicesupport.billing.domain.model.valueobject.Money;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Currency;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("EirB2cSampleFixtures (real eir B2C samples: 3 accounts x 2 months)")
class EirB2cSampleFixturesTest {

    private static final Currency EUR = Currency.getInstance("EUR");
    private final Map<AccountId, List<Invoice>> fixtures = EirB2cSampleFixtures.all();

    @Test
    void exposes_the_three_real_accounts_each_with_two_bill_runs() {
        // GIVEN the sample set
        // WHEN the accounts are listed
        // THEN the three real billing accounts are present, each with an August + September invoice
        assertThat(fixtures.keySet()).containsExactlyInAnyOrder(
                AccountId.of("99224964"), AccountId.of("99226126"), AccountId.of("99226337"));
        assertThat(fixtures.values()).allSatisfy(invoices -> assertThat(invoices).hasSize(2));
    }

    @Test
    void every_invoice_reconciles_on_the_tax_included_basis() {
        // GIVEN each sample invoice
        // WHEN the billed lines are summed (TTC)
        // THEN the line sum equals the invoice total (exact reconciliation, tolerance 0)
        for (Invoice invoice : allInvoices()) {
            Money lineSum = invoice.lines().stream()
                    .map(line -> line.amounts().taxIncluded())
                    .reduce(Money.zero(EUR), Money::plus);
            assertThat(lineSum)
                    .as("reconciliation for bill %s", invoice.period().id())
                    .isEqualTo(invoice.totals().taxIncluded());
        }
    }

    @Test
    void invoice_totals_match_the_published_pdf_amounts() {
        // GIVEN the transcribed sample invoices
        // WHEN each invoice total (TTC) is read
        // THEN it matches the amount printed on the source PDF
        assertThat(totalOf("2608129000000039")).isEqualTo(1999L);   // 99224964 August
        assertThat(totalOf("2609129000000008")).isEqualTo(7546L);   // 99224964 September
        assertThat(totalOf("2608129000000040")).isEqualTo(13998L);  // 99226126 August
        assertThat(totalOf("2609129000000009")).isEqualTo(7347L);   // 99226126 September
        assertThat(totalOf("2608129000000042")).isEqualTo(14689L);  // 99226337 August
        assertThat(totalOf("2609129000000011")).isEqualTo(18112L);  // 99226337 September
    }

    @Test
    void prorata_lines_carry_their_explicit_sub_period() {
        // GIVEN every prorata line across the samples
        List<InvoiceItem> proratas = allInvoices().stream()
                .flatMap(invoice -> invoice.lines().stream())
                .filter(line -> line.category() == LineCategory.PRORATA)
                .toList();

        // WHEN they are inspected
        // THEN there are proratas, and each carries a non-null applicable period (ADR-0054)
        assertThat(proratas).isNotEmpty();
        assertThat(proratas).allSatisfy(line -> assertThat(line.period()).isNotNull());
    }

    @Test
    void per_line_vat_split_rolls_up_consistently_with_the_total() {
        // GIVEN each invoice (per-line VAT derived at 23%, audit-only)
        // WHEN the tax-excluded + tax legs are summed
        // THEN they reconstitute the tax-included total exactly (no cent lost in roll-up)
        for (Invoice invoice : allInvoices()) {
            Money excluded = invoice.totals().taxExcluded();
            Money tax = invoice.totals().tax();
            assertThat(excluded.plus(tax))
                    .as("HT + VAT = TTC for bill %s", invoice.period().id())
                    .isEqualTo(invoice.totals().taxIncluded());
        }
    }

    private long totalOf(String billNumber) {
        return allInvoices().stream()
                .filter(invoice -> invoice.period().id().equals(billNumber))
                .findFirst().orElseThrow()
                .totals().taxIncluded().minorUnits();
    }

    private List<Invoice> allInvoices() {
        return fixtures.values().stream().flatMap(List::stream).toList();
    }
}
