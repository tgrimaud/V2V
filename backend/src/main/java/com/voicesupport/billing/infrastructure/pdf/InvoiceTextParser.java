package com.voicesupport.billing.infrastructure.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
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

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;

// Deterministic parser from the invoice PDF's extracted text to the domain Invoice, aligned with
// invoice-extraction-json.md (TASK-BE-064, ADR-0005). It reads a labeled line grammar — INVOICE /
// ACCOUNT / PERIOD / DATE / CURRENCY / LINE <category>|<label>|<amount> / VAT / TOTAL — amounts
// parsed to integer cents. Status mirrors the contract: UNUSABLE (FAILED) when a required field
// (invoice/account/period/date/total or any line) is missing; PARTIAL when lines do not reconcile
// with the total; SUCCESS (parseable) when they reconcile. The grammar is the stable contract the
// comparison engine consumes; the exact label set is tuned to the real Galaxion layout once sample
// PDFs arrive (OQ-003). Pure (no PDFBox) so it is unit-testable without generating a PDF, and it
// lives outside adapter.out (it is a parsing component, not an outbound adapter); the LLM never
// reads the PDF — parsing stays deterministic here (DEC-002).
public final class InvoiceTextParser implements PdfTextInvoiceParser {

    private static final Currency DEFAULT_CURRENCY = Currency.getInstance("EUR");

    @Override
    public ExtractionResult parse(String text, String documentReference) {
        Fields fields = new Fields(documentReference);
        for (String raw : text == null ? new String[0] : text.split("\\r?\\n")) {
            fields.consume(raw.strip());
        }
        List<String> missing = fields.missingRequired();
        if (!missing.isEmpty()) {
            return ExtractionResult.failed("unusable PDF: missing " + String.join(", ", missing));
        }
        return fields.toExtraction();
    }

    private static Long parseAmountCents(String raw) {
        String cleaned = raw.strip().replace("\u00A0", "").replace(" ", "").replace("€", "");
        if (cleaned.isBlank()) {
            return null;
        }
        String normalized = normalizeDecimal(cleaned);
        try {
            return new BigDecimal(normalized).movePointRight(2).setScale(0, RoundingMode.HALF_UP).longValueExact();
        } catch (RuntimeException invalid) {
            return null;
        }
    }

    // Normalizes mixed thousands/decimal separators: the separator that appears last is the decimal
    // one, the other is a thousands separator to drop. A lone comma is treated as the decimal point.
    private static String normalizeDecimal(String cleaned) {
        int lastComma = cleaned.lastIndexOf(',');
        int lastDot = cleaned.lastIndexOf('.');
        if (lastComma >= 0 && lastDot >= 0) {
            char decimal = lastComma > lastDot ? ',' : '.';
            char thousands = decimal == ',' ? '.' : ',';
            return cleaned.replace(String.valueOf(thousands), "").replace(decimal, '.');
        }
        return cleaned.replace(',', '.');
    }

    private static LineCategory mapCategory(String raw) {
        String key = raw.strip().toUpperCase().replace('-', '_').replace(' ', '_');
        try {
            return LineCategory.valueOf(key);
        } catch (IllegalArgumentException unknown) {
            return LineCategory.OTHER;
        }
    }

    // Single-pass accumulator for the labeled grammar. Private + mutable only within the parse call;
    // nothing escapes except the immutable ExtractionResult.
    private static final class Fields {

        private final String documentReference;
        private final List<ParsedLine> lines = new ArrayList<>();
        private String invoiceId;
        private String accountId;
        private String periodId;
        private LocalDate date;
        private Currency currency = DEFAULT_CURRENCY;
        private Long totalCents;
        private long vatCents;

        private Fields(String documentReference) {
            this.documentReference = documentReference;
        }

        private void consume(String line) {
            if (startsWith(line, "INVOICE ")) {
                invoiceId = value(line);
            } else if (startsWith(line, "ACCOUNT ")) {
                accountId = value(line);
            } else if (startsWith(line, "PERIOD ")) {
                periodId = value(line);
            } else if (startsWith(line, "DATE ")) {
                date = parseDate(value(line));
            } else if (startsWith(line, "CURRENCY ")) {
                currency = parseCurrency(value(line));
            } else if (startsWith(line, "LINE ")) {
                addLine(value(line));
            } else if (startsWith(line, "VAT ")) {
                Long cents = parseAmountCents(value(line));
                vatCents = cents == null ? 0L : cents;
            } else if (startsWith(line, "TOTAL ")) {
                totalCents = parseAmountCents(value(line));
            }
        }

        private void addLine(String payload) {
            String[] parts = payload.split("\\|", 3);
            if (parts.length < 3) {
                return;
            }
            Long cents = parseAmountCents(parts[2]);
            if (cents == null) {
                return;
            }
            lines.add(new ParsedLine(mapCategory(parts[0]), parts[1].strip(), cents));
        }

        private List<String> missingRequired() {
            List<String> missing = new ArrayList<>();
            if (isBlank(invoiceId)) missing.add("invoice");
            if (isBlank(accountId)) missing.add("account");
            if (isBlank(periodId)) missing.add("period");
            if (date == null) missing.add("date");
            if (totalCents == null) missing.add("total");
            if (lines.isEmpty()) missing.add("lines");
            return missing;
        }

        private ExtractionResult toExtraction() {
            Invoice invoice = buildInvoice();
            long sum = lines.stream().mapToLong(ParsedLine::cents).sum();
            if (sum != totalCents) {
                return ExtractionResult.partial(invoice, List.of(
                        "lines do not reconcile with the total: lines=" + sum + " total=" + totalCents));
            }
            return ExtractionResult.success(invoice);
        }

        private Invoice buildInvoice() {
            List<InvoiceItem> items = new ArrayList<>();
            for (int i = 0; i < lines.size(); i++) {
                items.add(lines.get(i).toItem("line-" + (i + 1), currency, documentReference));
            }
            LineAmounts totals = new LineAmounts(money(totalCents), money(totalCents - vatCents), money(vatCents));
            InvoiceGroup group = new InvoiceGroup("grp-1", "Charges", null, 0, totals, List.copyOf(items));
            InvoiceSection section = new InvoiceSection("sec-1", "Invoice", 0, true, totals, List.of(group));
            return new Invoice(InvoiceId.of(invoiceId), AccountId.of(accountId), InvoiceLevel.BILLING_ACCOUNT,
                    new BillingPeriod(periodId, date), totals, List.of(section));
        }

        private Money money(long cents) {
            return Money.ofMinorUnits(cents, currency);
        }

        private static boolean startsWith(String line, String prefix) {
            return line.length() >= prefix.length() && line.substring(0, prefix.length()).equalsIgnoreCase(prefix);
        }

        private static String value(String line) {
            return line.substring(line.indexOf(' ') + 1).strip();
        }

        private static boolean isBlank(String value) {
            return value == null || value.isBlank();
        }

        private static LocalDate parseDate(String raw) {
            try {
                return LocalDate.parse(raw.strip());
            } catch (RuntimeException invalid) {
                return null;
            }
        }

        private static Currency parseCurrency(String raw) {
            try {
                return Currency.getInstance(raw.strip().toUpperCase());
            } catch (RuntimeException invalid) {
                return DEFAULT_CURRENCY;
            }
        }
    }

    // One extracted LINE before it becomes an InvoiceItem. taxExcluded == taxIncluded and tax == 0 at
    // line level: VAT is exposed only at invoice level (same stance as EirBssBillingAdapter).
    private record ParsedLine(LineCategory category, String label, long cents) {

        private InvoiceItem toItem(String id, Currency currency, String documentReference) {
            Money ti = Money.ofMinorUnits(cents, currency);
            LineAmounts amounts = new LineAmounts(ti, ti, Money.zero(currency));
            return new InvoiceItem(id, null, null, null, category, amounts,
                    new Evidence("pdfbox", documentReference, label));
        }
    }
}
