package com.voicesupport.billing.infrastructure.fixtures;

import com.voicesupport.billing.domain.model.Invoice;
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

import java.time.LocalDate;
import java.util.Currency;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

// Synthetic BSS invoices for the six V1 journeys (customer-eir-001..006): nominal, discount expiry,
// usage overage, proration, insufficient data (single invoice), and unusable (no lines). Amounts are
// integer cents (TTC comparison basis), with a consistent tax split and roll-up so later
// reconciliation (TASK-BE-042) holds. Feeds the in-memory adapter (TASK-BE-040) and QA (TASK-QA-019).
public final class BssBillingFixtures {

    private static final Currency EUR = Currency.getInstance("EUR");
    private static final LocalDate PREVIOUS = LocalDate.of(2026, 1, 15);
    private static final LocalDate CURRENT = LocalDate.of(2026, 2, 15);

    private BssBillingFixtures() {
    }

    public static Map<AccountId, List<Invoice>> all() {
        Map<AccountId, List<Invoice>> byAccount = new LinkedHashMap<>();
        byAccount.put(AccountId.of("eir-001"), nominal());
        byAccount.put(AccountId.of("eir-002"), discountExpiry());
        byAccount.put(AccountId.of("eir-003"), usageOverage());
        byAccount.put(AccountId.of("eir-004"), proration());
        byAccount.put(AccountId.of("eir-005"), insufficientData());
        byAccount.put(AccountId.of("eir-006"), unusable());
        return Map.copyOf(byAccount);
    }

    private static List<Invoice> nominal() {
        List<InvoiceItem> stable = List.of(item("sub", LineCategory.SUBSCRIPTION, 3000L));
        return List.of(invoice("eir-001", "eir-001-2026-01", PREVIOUS, stable),
                invoice("eir-001", "eir-001-2026-02", CURRENT, stable));
    }

    private static List<Invoice> discountExpiry() {
        return List.of(
                invoice("eir-002", "eir-002-2026-01", PREVIOUS, List.of(
                        item("sub", LineCategory.SUBSCRIPTION, 3000L),
                        item("promo", LineCategory.DISCOUNT, -500L))),
                invoice("eir-002", "eir-002-2026-02", CURRENT, List.of(
                        item("sub", LineCategory.SUBSCRIPTION, 3000L))));
    }

    private static List<Invoice> usageOverage() {
        return List.of(
                invoice("eir-003", "eir-003-2026-01", PREVIOUS, List.of(
                        item("sub", LineCategory.SUBSCRIPTION, 3000L))),
                invoice("eir-003", "eir-003-2026-02", CURRENT, List.of(
                        item("sub", LineCategory.SUBSCRIPTION, 3000L),
                        item("data-overage", LineCategory.OVERAGE, 1200L))));
    }

    private static List<Invoice> proration() {
        return List.of(
                invoice("eir-004", "eir-004-2026-01", PREVIOUS, List.of(
                        item("sub", LineCategory.SUBSCRIPTION, 3000L))),
                invoice("eir-004", "eir-004-2026-02", CURRENT, List.of(
                        item("sub", LineCategory.SUBSCRIPTION, 3000L),
                        item("option-prorata", LineCategory.PRORATA, 800L))));
    }

    private static List<Invoice> insufficientData() {
        return List.of(invoice("eir-005", "eir-005-2026-02", CURRENT, List.of(
                item("sub", LineCategory.SUBSCRIPTION, 3000L))));
    }

    private static List<Invoice> unusable() {
        return List.of(
                invoice("eir-006", "eir-006-2026-01", PREVIOUS, List.of()),
                invoice("eir-006", "eir-006-2026-02", CURRENT, List.of()));
    }

    private static Invoice invoice(String account, String invoiceId, LocalDate date,
            List<InvoiceItem> items) {
        InvoiceGroup group = new InvoiceGroup(invoiceId + "-g", "Charges", null, 0, rollup(items), items);
        InvoiceSection section =
                new InvoiceSection(invoiceId + "-s", "Invoice", 0, true, rollup(items), List.of(group));
        return new Invoice(InvoiceId.of(invoiceId), AccountId.of(account), InvoiceLevel.BILLING_ACCOUNT,
                new BillingPeriod(invoiceId, date), rollup(items), List.of(section));
    }

    private static InvoiceItem item(String id, LineCategory category, long taxIncludedCents) {
        return new InvoiceItem(id, category.name(), id, "S", category, amount(taxIncludedCents),
                new Evidence("bss-fixture", null, category + " " + id));
    }

    private static LineAmounts amount(long taxIncludedCents) {
        long tax = taxIncludedCents / 6L;
        long taxExcluded = taxIncludedCents - tax;
        return new LineAmounts(cents(taxIncludedCents), cents(taxExcluded), cents(tax));
    }

    private static LineAmounts rollup(List<InvoiceItem> items) {
        return new LineAmounts(
                sum(items, line -> line.amounts().taxIncluded()),
                sum(items, line -> line.amounts().taxExcluded()),
                sum(items, line -> line.amounts().tax()));
    }

    private static Money sum(List<InvoiceItem> items, Function<InvoiceItem, Money> component) {
        return items.stream().map(component).reduce(Money.zero(EUR), Money::plus);
    }

    private static Money cents(long value) {
        return Money.ofMinorUnits(value, EUR);
    }
}
