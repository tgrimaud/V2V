package com.voicesupport.billing.infrastructure.fixtures;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceGroup;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.InvoiceSection;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingPeriod;
import com.voicesupport.billing.domain.model.valueobject.DateRange;
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

// Realistic mock invoices transcribed from the anonymized eir B2C sample PDFs (TASK-BE-059,
// eir-b2c-invoice-samples.md): three real billing accounts, two consecutive bill runs each (August /
// September 2026). Amounts are integer cents on the tax-included basis (the customer-facing
// comparison basis); per-line VAT is derived at the invoice's 23% rate for audit only, since the eir
// B2C PDF exposes VAT only at invoice level. Each invoice reconciles exactly (sum of line TTC =
// invoice total TTC). Proratas carry their explicit sub-period; recurring and prorated variants of
// the same product use distinct codes so the comparison engine matches them line-for-line.
public final class EirB2cSampleFixtures {

    private static final Currency EUR = Currency.getInstance("EUR");
    private static final LocalDate ISSUE = LocalDate.of(2026, 9, 25);
    private static final DateRange AUG_USAGE = DateRange.of(d(8, 12), d(9, 11));
    private static final DateRange AUG_CHARGE = DateRange.of(d(9, 12), d(10, 11));
    private static final DateRange SEP_USAGE = DateRange.of(d(9, 12), d(10, 11));
    private static final DateRange SEP_CHARGE = DateRange.of(d(10, 12), d(11, 11));

    private EirB2cSampleFixtures() {
    }

    public static Map<AccountId, List<Invoice>> all() {
        Map<AccountId, List<Invoice>> byAccount = new LinkedHashMap<>();
        byAccount.put(AccountId.of("99224964"), List.of(mobileAugust(), mobileSeptember()));
        byAccount.put(AccountId.of("99226126"), List.of(fibreAugust(), fibreTvSeptember()));
        byAccount.put(AccountId.of("99226337"), List.of(fibreTvAugust(), fibreTvMobileSeptember()));
        return Map.copyOf(byAccount);
    }

    // --- 99224964 : single mobile line (subscription + expiring discount), grows with bundles + roaming.

    private static Invoice mobileAugust() {
        InvoiceGroup subs = grp("aug-subs", "Subscription and options", AUG_CHARGE, List.of(
                it("mobile-connect-30d", "eir Mobile Connect - 30 Day", LineCategory.SUBSCRIPTION, 2999),
                it("mobile-connect-10-discount", "\u20ac10 discount for 12 months ends August '27",
                        LineCategory.DISCOUNT, -1000)));
        return inv("99224964", "2608129000000039", AUG_USAGE, AUG_CHARGE,
                List.of(sec("mobile", "085 7092782 eir Mobile Connect - 30 Day", 0, List.of(subs))));
    }

    private static Invoice mobileSeptember() {
        InvoiceGroup subs = grp("sep-subs", "Subscription and options", SEP_CHARGE, List.of(
                it("mobile-connect-30d", "eir Mobile Connect - 30 Day", LineCategory.SUBSCRIPTION, 2999),
                it("mobile-connect-10-discount", "\u20ac10 discount for 12 months ends August '27",
                        LineCategory.DISCOUNT, -1000),
                it("15gb-bundle-prorata", "15GB Bundle from 25 Sep 26 until 11 Oct 26", LineCategory.PRORATA,
                        850, DateRange.of(d(9, 25), d(10, 11))),
                it("15gb-bundle", "15GB Bundle", LineCategory.OPTION, 1499),
                it("mobile-security", "eir Mobile Security", LineCategory.OPTION, 199)));
        InvoiceGroup oneOff = grp("sep-oneoff", "One-time charges and adjustments", SEP_USAGE, List.of(
                it("roaming-1gb-usa-canada", "1GB USA/Canada Roaming Bundle 25 Sep 26", LineCategory.ONE_OFF, 2999)));
        return inv("99224964", "2609129000000008", SEP_USAGE, SEP_CHARGE,
                List.of(sec("mobile", "085 7092782 eir Mobile Connect - 30 Day", 0, List.of(subs, oneOff))));
    }

    // --- 99226126 : fibre + one-time installation (Aug), then fibre + new eir TV service (Sep).

    private static Invoice fibreAugust() {
        InvoiceGroup subs = grp("aug-fibre-subs", "Subscription and options", AUG_CHARGE, List.of(
                it("fibre-1gb", "eir Fibre 1GB NBI with off peak calls", LineCategory.SUBSCRIPTION, 8599),
                it("fibre-46-discount", "\u20ac46 discount for 24 months ends September '28",
                        LineCategory.DISCOUNT, -4600)));
        InvoiceGroup oneOff = grp("aug-fibre-oneoff", "One-time charges and adjustments", AUG_USAGE, List.of(
                it("ftth-installation", "Fibre to the Home Installation Fee 06 Sep 26", LineCategory.ONE_OFF, 9999)));
        return inv("99226126", "2608129000000040", AUG_USAGE, AUG_CHARGE,
                List.of(sec("fibre", "076-1089762 eir Fibre 1Gb with off peak calls - 24 month offer", 0,
                        List.of(subs, oneOff))));
    }

    private static Invoice fibreTvSeptember() {
        InvoiceGroup fibre = grp("sep-fibre-subs", "Subscription and options", SEP_CHARGE, List.of(
                it("fibre-1gb", "eir Fibre 1GB NBI with off peak calls", LineCategory.SUBSCRIPTION, 8599),
                it("fibre-46-discount", "\u20ac46 discount for 24 months ends September '28",
                        LineCategory.DISCOUNT, -4600)));
        InvoiceGroup tv = grp("sep-tv-subs", "Subscription and options", SEP_CHARGE, List.of(
                it("tv-prorata", "eir TV from 25 Sep 26 until 11 Oct 26", LineCategory.PRORATA, 1133,
                        DateRange.of(d(9, 25), d(10, 11))),
                it("tv", "eir TV", LineCategory.SUBSCRIPTION, 1999),
                it("tv-5-discount-prorata", "eir TV - \u20ac5 discount ends September '27 from 25 Sep until 11 Oct",
                        LineCategory.DISCOUNT, -283, DateRange.of(d(9, 25), d(10, 11))),
                it("tv-5-discount", "eir TV - \u20ac5 discount for 12 months ends September '27",
                        LineCategory.DISCOUNT, -500),
                it("tv-extra-pack", "eir TV Extra pack", LineCategory.OPTION, 999)));
        return inv("99226126", "2609129000000009", SEP_USAGE, SEP_CHARGE, List.of(
                sec("fibre", "076-1089762 eir Fibre 1Gb with off peak calls - 24 month offer", 0, List.of(fibre)),
                sec("tv", "eir TV - 12 month offer", 1, List.of(tv))));
    }

    // --- 99226337 : fibre + TV + one-time activation (Aug), then fibre + TV + new mobile (Sep).

    private static Invoice fibreTvAugust() {
        InvoiceGroup fibre = grp("aug-fibre-subs", "Subscription and options", AUG_CHARGE, List.of(
                it("fibre-1gb", "eir Fibre 1GB - Unlimited broadband usage. Unlimited off peak local and national calls",
                        LineCategory.SUBSCRIPTION, 8599),
                it("fibre-46-discount", "\u20ac46 discount for 24 months ends September '28",
                        LineCategory.DISCOUNT, -4600)));
        InvoiceGroup oneOff = grp("aug-fibre-oneoff", "One-time charges and adjustments", AUG_USAGE, List.of(
                it("broadband-activation", "Broadband activation fee 08 Sep 26", LineCategory.ONE_OFF, 4999)));
        InvoiceGroup tv = grp("aug-tv-subs", "Subscription and options", AUG_CHARGE, List.of(
                it("tv-prorata", "eir TV from 08 Sep 26 until 11 Sep 26", LineCategory.PRORATA, 258,
                        DateRange.of(d(9, 8), d(9, 11))),
                it("tv", "eir TV", LineCategory.SUBSCRIPTION, 1999),
                it("tv-5-discount-prorata", "eir TV - \u20ac5 discount ends September '28 from 08 Sep until 11 Sep",
                        LineCategory.DISCOUNT, -64, DateRange.of(d(9, 8), d(9, 11))),
                it("tv-5-discount", "eir TV - \u20ac5 discount for 24 months ends September '28",
                        LineCategory.DISCOUNT, -500),
                it("racing-tv-pack", "Racing TV pack", LineCategory.OPTION, 2999),
                it("tv-extra-pack", "eir TV Extra pack", LineCategory.OPTION, 999)));
        return inv("99226337", "2608129000000042", AUG_USAGE, AUG_CHARGE, List.of(
                sec("fibre", "076-1090247 eir Fibre 1Gb with off peak calls", 0, List.of(fibre, oneOff)),
                sec("tv", "eir TV - 24 month offer", 1, List.of(tv))));
    }

    private static Invoice fibreTvMobileSeptember() {
        InvoiceGroup fibre = grp("sep-fibre-subs", "Subscription and options", SEP_CHARGE, List.of(
                it("fibre-1gb", "eir Fibre 1GB - Unlimited broadband usage. Unlimited off peak local and national calls",
                        LineCategory.SUBSCRIPTION, 8599),
                it("fibre-46-discount", "\u20ac46 discount for 24 months ends September '28",
                        LineCategory.DISCOUNT, -4600)));
        InvoiceGroup tv = grp("sep-tv-subs", "Subscription and options", SEP_CHARGE, List.of(
                it("tv", "eir TV", LineCategory.SUBSCRIPTION, 1999),
                it("tv-5-discount", "eir TV - \u20ac5 discount for 24 months ends September '28",
                        LineCategory.DISCOUNT, -500),
                it("racing-tv-pack", "Racing TV pack", LineCategory.OPTION, 2999),
                it("tv-extra-pack", "eir TV Extra pack", LineCategory.OPTION, 999)));
        InvoiceGroup mobile = grp("sep-mobile-subs", "Subscription and options", SEP_CHARGE, List.of(
                it("mobile-5g-prorata", "eir Mobile Connect Plus 5G from 25 Sep 26 until 11 Oct 26",
                        LineCategory.PRORATA, 3683, DateRange.of(d(9, 25), d(10, 11))),
                it("mobile-5g", "eir Mobile Connect Plus 5G", LineCategory.SUBSCRIPTION, 6499),
                it("mobile-bb-discount-prorata", "\u20ac10 discount when ordering mobile with Broadband from 25 Sep until 11 Oct",
                        LineCategory.DISCOUNT, -566, DateRange.of(d(9, 25), d(10, 11))),
                it("mobile-bb-discount", "\u20ac10 discount when ordering mobile with Broadband",
                        LineCategory.DISCOUNT, -1000)));
        return inv("99226337", "2609129000000011", SEP_USAGE, SEP_CHARGE, List.of(
                sec("fibre", "076-1090247 eir Fibre 1Gb with off peak calls", 0, List.of(fibre)),
                sec("tv", "eir TV - 24 month offer", 1, List.of(tv)),
                sec("mobile", "085 8923313 eir Mobile Connect Plus 5G", 2, List.of(mobile))));
    }

    // --- builders -------------------------------------------------------------------------------

    private static LocalDate d(int month, int day) {
        return LocalDate.of(2026, month, day);
    }

    private static InvoiceItem it(String code, String label, LineCategory category, long taxIncludedCents) {
        return it(code, label, category, taxIncludedCents, null);
    }

    private static InvoiceItem it(String code, String label, LineCategory category, long taxIncludedCents,
            DateRange period) {
        return new InvoiceItem(code, category.name(), code, "S", category, amount23(taxIncludedCents),
                new Evidence("bss-fixture-eir", label, label), period);
    }

    private static InvoiceGroup grp(String id, String name, DateRange period, List<InvoiceItem> items) {
        return new InvoiceGroup(id, name, null, 0, rollupItems(items), items, period);
    }

    private static InvoiceSection sec(String id, String name, int order, List<InvoiceGroup> groups) {
        return new InvoiceSection(id, name, order, true, rollupGroups(groups), groups);
    }

    private static Invoice inv(String account, String bill, DateRange usage, DateRange charge,
            List<InvoiceSection> sections) {
        return new Invoice(InvoiceId.of(bill), AccountId.of(account), InvoiceLevel.BILLING_ACCOUNT,
                new BillingPeriod(bill, ISSUE, usage, charge), rollupSections(sections), sections);
    }

    private static LineAmounts rollupItems(List<InvoiceItem> items) {
        return sumAmounts(items.stream().map(InvoiceItem::amounts).toList());
    }

    private static LineAmounts rollupGroups(List<InvoiceGroup> groups) {
        return sumAmounts(groups.stream().map(InvoiceGroup::amounts).toList());
    }

    private static LineAmounts rollupSections(List<InvoiceSection> sections) {
        return sumAmounts(sections.stream().map(InvoiceSection::amounts).toList());
    }

    private static LineAmounts sumAmounts(List<LineAmounts> parts) {
        Money taxIncluded = Money.zero(EUR);
        Money taxExcluded = Money.zero(EUR);
        Money tax = Money.zero(EUR);
        for (LineAmounts part : parts) {
            taxIncluded = taxIncluded.plus(part.taxIncluded());
            taxExcluded = taxExcluded.plus(part.taxExcluded());
            tax = tax.plus(part.tax());
        }
        return new LineAmounts(taxIncluded, taxExcluded, tax);
    }

    private static LineAmounts amount23(long taxIncludedCents) {
        long taxExcluded = Math.round(taxIncludedCents / 1.23);
        long tax = taxIncludedCents - taxExcluded;
        return new LineAmounts(cents(taxIncludedCents), cents(taxExcluded), cents(tax));
    }

    private static Money cents(long value) {
        return Money.ofMinorUnits(value, EUR);
    }
}
