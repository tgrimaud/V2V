package com.voicesupport.billing.infrastructure.pdf;

import com.voicesupport.billing.domain.model.valueobject.DateRange;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;
import com.voicesupport.billing.domain.model.valueobject.Money;

import java.time.LocalDate;
import java.util.Currency;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

// Static text helpers for the real eir B2C invoice layout (TASK-BE-065). Pure and side-effect free so
// the layout parser stays small and unit-testable. Dates read "25 Sep 26"; amounts are the trailing
// 2-decimal value of a line (never the "€10"/"€46" discount tokens embedded in a label, which carry no
// decimals); per-line VAT is derived at the invoice's 23% rate (G1 in eir-b2c-invoice-samples.md), the
// same split EirB2cSampleFixtures uses so roll-ups reconcile exactly on the tax-included basis.
final class EirInvoiceText {

    static final Currency EUR = Currency.getInstance("EUR");

    private static final Map<String, Integer> MONTHS = Map.ofEntries(
            Map.entry("jan", 1), Map.entry("feb", 2), Map.entry("mar", 3), Map.entry("apr", 4),
            Map.entry("may", 5), Map.entry("jun", 6), Map.entry("jul", 7), Map.entry("aug", 8),
            Map.entry("sep", 9), Map.entry("oct", 10), Map.entry("nov", 11), Map.entry("dec", 12));

    private static final Pattern DATE = Pattern.compile("(\\d{1,2})\\s+([A-Za-z]{3})\\s+(\\d{2})");
    private static final Pattern TRAILING_AMOUNT = Pattern.compile("(-?\\d{1,3}(?:,\\d{3})*\\.\\d{2})\\s*$");
    private static final Pattern SUBTOTAL = Pattern.compile("^\\u20AC\\s*-?\\d{1,3}(?:,\\d{3})*\\.\\d{2}$");
    private static final Pattern GROUP_PERIOD = Pattern.compile("for the period from (.+?) to (.+?)\\s*$");
    private static final Pattern LINE_PERIOD = Pattern.compile("from (\\d{1,2}\\s+[A-Za-z]{3}\\s+\\d{2}) until (\\d{1,2}\\s+[A-Za-z]{3}\\s+\\d{2})");

    private EirInvoiceText() {
    }

    static LocalDate parseDate(String raw) {
        if (raw == null) {
            return null;
        }
        Matcher matcher = DATE.matcher(raw.strip());
        if (!matcher.find()) {
            return null;
        }
        Integer month = MONTHS.get(matcher.group(2).toLowerCase());
        if (month == null) {
            return null;
        }
        return LocalDate.of(2000 + Integer.parseInt(matcher.group(3)), month, Integer.parseInt(matcher.group(1)));
    }

    static Long trailingAmountCents(String line) {
        Matcher matcher = TRAILING_AMOUNT.matcher(line);
        if (!matcher.find()) {
            return null;
        }
        String normalized = matcher.group(1).replace(",", "");
        return new java.math.BigDecimal(normalized).movePointRight(2).longValueExact();
    }

    static String stripTrailingAmount(String line) {
        return TRAILING_AMOUNT.matcher(line).replaceAll("").strip();
    }

    static boolean isSubtotal(String line) {
        return SUBTOTAL.matcher(line.strip()).matches();
    }

    // Returns the group name ("Subscription and options" / "One-time charges and adjustments") + its
    // billed window if the line is a group header, else null.
    static GroupHeader groupHeader(String line) {
        String name = groupName(line);
        if (name == null) {
            return null;
        }
        Matcher matcher = GROUP_PERIOD.matcher(line);
        DateRange period = matcher.find() ? range(matcher.group(1), matcher.group(2)) : null;
        return new GroupHeader(name, period);
    }

    static DateRange linePeriod(String label) {
        Matcher matcher = LINE_PERIOD.matcher(label);
        if (!matcher.find()) {
            return null;
        }
        return range(matcher.group(1), matcher.group(2));
    }

    // Per-line amounts on the tax-included basis with VAT derived at 23% (G1), identical to
    // EirB2cSampleFixtures.amount23 so parser roll-ups equal the fixture roll-ups exactly.
    static LineAmounts amount23(long taxIncludedCents) {
        long taxExcluded = Math.round(taxIncludedCents / 1.23);
        long tax = taxIncludedCents - taxExcluded;
        return new LineAmounts(cents(taxIncludedCents), cents(taxExcluded), cents(tax));
    }

    static LineAmounts rollup(List<LineAmounts> parts) {
        Money ti = Money.zero(EUR);
        Money te = Money.zero(EUR);
        Money tax = Money.zero(EUR);
        for (LineAmounts part : parts) {
            ti = ti.plus(part.taxIncluded());
            te = te.plus(part.taxExcluded());
            tax = tax.plus(part.tax());
        }
        return new LineAmounts(ti, te, tax);
    }

    static Money cents(long value) {
        return Money.ofMinorUnits(value, EUR);
    }

    private static String groupName(String line) {
        if (line.startsWith("Subscription and options")) {
            return "Subscription and options";
        }
        if (line.startsWith("One-time charges and adjustments")) {
            return "One-time charges and adjustments";
        }
        return null;
    }

    private static DateRange range(String start, String end) {
        LocalDate from = parseDate(start);
        LocalDate to = parseDate(end);
        return from != null && to != null ? DateRange.of(from, to) : null;
    }

    record GroupHeader(String name, DateRange period) {
    }
}
