package com.voicesupport.billing.infrastructure.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceSection;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingPeriod;
import com.voicesupport.billing.domain.model.valueobject.DateRange;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceLevel;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

// Real eir B2C invoice-PDF parser (TASK-BE-065, pdf.source=eir-b2c), tuned to the layout documented in
// eir-b2c-invoice-samples.md: an "at a glance" header (billing account, bill number, billing + usage +
// monthly charge windows, the VAT-included total) and a "Detail of your eir service" body of per-service
// sections and Subscription/One-time groups (EirInvoiceBodyReader). Per-line VAT is derived at 23% (G1).
// Status: FAILED when the header or any service line is missing (unusable); PARTIAL when the parsed lines
// do not reconcile with the invoice's stated total; SUCCESS otherwise. The LLM never reads the PDF (DEC-002).
public final class EirB2cInvoiceLayoutParser implements PdfTextInvoiceParser {

    private static final Pattern ACCOUNT = Pattern.compile("^Billing account (\\d+)$");
    private static final Pattern BILL = Pattern.compile("^Bill number (\\S+)$");
    private static final Pattern WINDOW = Pattern.compile("(.+?)\\s+-\\s+(.+?)$");

    @Override
    public ExtractionResult parse(String text, String documentReference) {
        if (text == null || text.isBlank()) {
            return ExtractionResult.failed("empty eir invoice: " + documentReference);
        }
        List<String> lines = text.lines().map(String::strip).toList();
        Header header = parseHeader(lines);
        List<String> missing = header.missing();
        if (!missing.isEmpty()) {
            return ExtractionResult.failed("unusable eir invoice: missing " + String.join(", ", missing));
        }
        List<InvoiceSection> sections = new EirInvoiceBodyReader(documentReference).read(lines);
        if (sections.isEmpty()) {
            return ExtractionResult.failed("unusable eir invoice: no service lines");
        }
        return reconcile(header, assemble(header, sections));
    }

    private Header parseHeader(List<String> lines) {
        Header header = new Header();
        for (String line : lines) {
            header.consume(line);
        }
        return header;
    }

    private Invoice assemble(Header header, List<InvoiceSection> sections) {
        List<LineAmounts> parts = sections.stream().map(InvoiceSection::amounts).toList();
        BillingPeriod period = new BillingPeriod(header.bill, header.billingDate, header.usage, header.charge);
        return new Invoice(InvoiceId.of(header.bill), AccountId.of(header.account),
                InvoiceLevel.BILLING_ACCOUNT, period, EirInvoiceText.rollup(parts), sections);
    }

    private ExtractionResult reconcile(Header header, Invoice invoice) {
        long rolledUp = invoice.totals().taxIncluded().minorUnits();
        if (header.statedTotalCents != null && rolledUp != header.statedTotalCents) {
            return ExtractionResult.partial(invoice, List.of(
                    "lines do not reconcile with the stated total: lines=" + rolledUp
                            + " stated=" + header.statedTotalCents));
        }
        return ExtractionResult.success(invoice);
    }

    private static final class Header {
        private String account;
        private String bill;
        private LocalDate billingDate;
        private DateRange usage;
        private DateRange charge;
        private Long statedTotalCents;

        private void consume(String line) {
            Matcher account = ACCOUNT.matcher(line);
            Matcher bill = BILL.matcher(line);
            if (this.account == null && account.matches()) {
                this.account = account.group(1);
            } else if (this.bill == null && bill.matches()) {
                this.bill = bill.group(1);
            } else if (this.billingDate == null && line.startsWith("Billing date ")) {
                this.billingDate = EirInvoiceText.parseDate(line.substring("Billing date ".length()));
            } else if (this.usage == null && line.startsWith("Usage period ")) {
                this.usage = window(line.substring("Usage period ".length()));
            } else if (this.charge == null && line.startsWith("Monthly charge period ")) {
                this.charge = window(line.substring("Monthly charge period ".length()));
            } else if (this.statedTotalCents == null && line.startsWith("Your bill for this month")) {
                this.statedTotalCents = EirInvoiceText.trailingAmountCents(line);
            }
        }

        private List<String> missing() {
            List<String> missing = new ArrayList<>();
            if (account == null || account.isBlank()) missing.add("billing account");
            if (bill == null || bill.isBlank()) missing.add("bill number");
            if (billingDate == null) missing.add("billing date");
            return missing;
        }

        private static DateRange window(String raw) {
            Matcher matcher = WINDOW.matcher(raw.strip());
            if (!matcher.matches()) {
                return null;
            }
            LocalDate start = EirInvoiceText.parseDate(matcher.group(1));
            LocalDate end = EirInvoiceText.parseDate(matcher.group(2));
            return start != null && end != null ? DateRange.of(start, end) : null;
        }
    }
}
