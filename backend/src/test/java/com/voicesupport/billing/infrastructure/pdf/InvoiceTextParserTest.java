package com.voicesupport.billing.infrastructure.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.ExtractionStatus;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class InvoiceTextParserTest {

    private final InvoiceTextParser parser = new InvoiceTextParser();

    private static final String VALID = String.join("\n",
            "INVOICE 113444",
            "ACCOUNT 99224964",
            "PERIOD 202608",
            "DATE 2026-08-01",
            "CURRENCY EUR",
            "LINE SUBSCRIPTION|Mobile plan|39,99",
            "LINE OPTION|Extra data|5,00",
            "VAT 8,40",
            "TOTAL 44,99");

    @Test
    void parse_reconciledInvoice_isSuccessWithTheExpectedTreeAndAmounts() {
        // GIVEN a complete invoice whose lines sum to the total
        // WHEN the text is parsed
        ExtractionResult result = parser.parse(VALID, "doc-uuid-1");

        // THEN it is a SUCCESS carrying the invoice with the parsed identity, period and amounts
        assertEquals(ExtractionStatus.SUCCESS, result.status());
        Invoice invoice = result.invoice();
        assertEquals("113444", invoice.id().value());
        assertEquals("99224964", invoice.accountId().value());
        assertEquals("202608", invoice.period().id());
        assertEquals(LocalDate.of(2026, 8, 1), invoice.period().invoiceDate());
        assertEquals(4499L, invoice.totals().taxIncluded().minorUnits());
        assertEquals(840L, invoice.totals().tax().minorUnits());
        assertEquals(3659L, invoice.totals().taxExcluded().minorUnits());
        List<InvoiceItem> lines = invoice.lines();
        assertEquals(2, lines.size());
        assertEquals(LineCategory.SUBSCRIPTION, lines.get(0).category());
        assertEquals(3999L, lines.get(0).amounts().taxIncluded().minorUnits());
        assertEquals("pdfbox", lines.get(0).evidence().source());
        assertEquals("doc-uuid-1", lines.get(0).evidence().documentReference());
    }

    @Test
    void parse_linesThatDoNotReconcileWithTheTotal_isPartialWithAnIssue() {
        // GIVEN the total does not equal the sum of the lines
        String text = VALID.replace("TOTAL 44,99", "TOTAL 50,00");

        // WHEN the text is parsed THEN it is PARTIAL and keeps the invoice + an explanatory issue
        ExtractionResult result = parser.parse(text, "doc-uuid-2");
        assertEquals(ExtractionStatus.PARTIAL, result.status());
        assertTrue(result.hasInvoice());
        assertFalse(result.issues().isEmpty());
        assertTrue(result.issues().get(0).contains("reconcile"));
    }

    @Test
    void parse_missingTotal_isFailedUnusable() {
        // GIVEN an invoice with no TOTAL line
        String text = VALID.replace("TOTAL 44,99", "");

        // WHEN parsed THEN it is FAILED (unusable) and carries no invoice
        ExtractionResult result = parser.parse(text, "doc-uuid-3");
        assertEquals(ExtractionStatus.FAILED, result.status());
        assertFalse(result.hasInvoice());
        assertTrue(result.issues().get(0).contains("total"));
    }

    @Test
    void parse_noLines_isFailedUnusable() {
        // GIVEN the required headers but no LINE entries
        String text = String.join("\n",
                "INVOICE 1", "ACCOUNT 2", "PERIOD 202601", "DATE 2026-01-01", "TOTAL 10,00");

        // WHEN parsed THEN it is FAILED (unusable) listing the missing lines
        ExtractionResult result = parser.parse(text, "doc-uuid-4");
        assertEquals(ExtractionStatus.FAILED, result.status());
        assertTrue(result.issues().get(0).contains("lines"));
    }

    @Test
    void parse_amountsWithThousandsSeparatorsAndDotDecimals_areParsedToCents() {
        // GIVEN amounts using space thousands separators and a dot decimal
        String text = String.join("\n",
                "INVOICE 9", "ACCOUNT 9", "PERIOD 202601", "DATE 2026-01-01",
                "LINE USAGE|Big usage|1 234.50", "TOTAL 1 234.50");

        // WHEN parsed THEN the amount is exact integer cents and reconciles
        ExtractionResult result = parser.parse(text, "doc-uuid-5");
        assertEquals(ExtractionStatus.SUCCESS, result.status());
        assertEquals(123450L, result.invoice().totals().taxIncluded().minorUnits());
    }

    @Test
    void parse_unknownCategory_fallsBackToOther() {
        // GIVEN a LINE with a category outside the enum
        String text = String.join("\n",
                "INVOICE 9", "ACCOUNT 9", "PERIOD 202601", "DATE 2026-01-01",
                "LINE WIDGETS|Mystery charge|1,00", "TOTAL 1,00");

        // WHEN parsed THEN the line maps to OTHER (never throws)
        ExtractionResult result = parser.parse(text, "doc-uuid-6");
        assertEquals(ExtractionStatus.SUCCESS, result.status());
        assertEquals(LineCategory.OTHER, result.invoice().lines().get(0).category());
    }

    @Test
    void parse_hyphenatedCategory_isNormalizedToTheEnum() {
        // GIVEN a "one-off" category label
        String text = String.join("\n",
                "INVOICE 9", "ACCOUNT 9", "PERIOD 202601", "DATE 2026-01-01",
                "LINE one-off|Setup fee|1,00", "TOTAL 1,00");

        // WHEN parsed THEN it maps to ONE_OFF
        ExtractionResult result = parser.parse(text, "doc-uuid-7");
        assertEquals(LineCategory.ONE_OFF, result.invoice().lines().get(0).category());
    }
}
