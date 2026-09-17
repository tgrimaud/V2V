package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingPeriod;
import com.voicesupport.billing.domain.model.valueobject.Evidence;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceLevel;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;
import com.voicesupport.billing.domain.model.valueobject.Money;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("Invoice aggregate (BSS hierarchy)")
class InvoiceTest {

    private static final Currency EUR = Currency.getInstance("EUR");

    @Test
    void lines_flattens_all_items_across_sections_and_groups() {
        // GIVEN an invoice with two sections, each holding a group with one item
        InvoiceItem subscription = item("it-1", LineCategory.SUBSCRIPTION, 3000L);
        InvoiceItem discount = item("it-2", LineCategory.DISCOUNT, -500L);
        Invoice invoice = invoiceWith(List.of(
                section("sec-1", group("grp-1", subscription)),
                section("sec-2", group("grp-2", discount))));

        // WHEN the billed leaves are flattened
        List<InvoiceItem> lines = invoice.lines();

        // THEN every item is returned in tree order
        assertThat(lines).containsExactly(subscription, discount);
    }

    @Test
    void sections_list_is_defensively_copied_and_unmodifiable() {
        // GIVEN a mutable sections list passed to the invoice
        List<InvoiceSection> mutable = new ArrayList<>(List.of(section("sec-1", group("grp-1",
                item("it-1", LineCategory.SUBSCRIPTION, 3000L)))));
        Invoice invoice = invoiceWith(mutable);

        // WHEN the caller mutates the original list afterwards
        mutable.clear();

        // THEN the invoice keeps its own copy, and that copy cannot be mutated
        assertThat(invoice.sections()).hasSize(1);
        assertThatThrownBy(() -> invoice.sections().add(section("x", group("g", item("i",
                LineCategory.OTHER, 0L))))).isInstanceOf(UnsupportedOperationException.class);
    }

    @Test
    void throws_when_a_required_field_is_null() {
        // GIVEN / WHEN / THEN a null accountId is rejected at construction
        assertThatThrownBy(() -> new Invoice(InvoiceId.of("inv-1"), null, InvoiceLevel.BILLING_ACCOUNT,
                new BillingPeriod("p-1", LocalDate.of(2026, 1, 1)), amounts(3000L), List.of()))
                .isInstanceOf(NullPointerException.class);
    }

    private static Invoice invoiceWith(List<InvoiceSection> sections) {
        return new Invoice(InvoiceId.of("inv-1"), AccountId.of("acc-1"), InvoiceLevel.BILLING_ACCOUNT,
                new BillingPeriod("p-1", LocalDate.of(2026, 1, 1)), amounts(3000L), sections);
    }

    private static InvoiceSection section(String id, InvoiceGroup group) {
        return new InvoiceSection(id, id + "-name", 0, true, amounts(0L), List.of(group));
    }

    private static InvoiceGroup group(String id, InvoiceItem item) {
        return new InvoiceGroup(id, id + "-name", null, 0, amounts(0L), List.of(item));
    }

    private static InvoiceItem item(String id, LineCategory category, long minorUnits) {
        return new InvoiceItem(id, "type", "code", "S", category, amounts(minorUnits),
                new Evidence("fixture", null, "line " + id));
    }

    private static LineAmounts amounts(long taxIncludedMinorUnits) {
        return new LineAmounts(Money.ofMinorUnits(taxIncludedMinorUnits, EUR),
                Money.ofMinorUnits(taxIncludedMinorUnits, EUR), Money.zero(EUR));
    }
}
