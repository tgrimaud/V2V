package com.voicesupport.billing.infrastructure.adapter.out.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.ExtractionStatus;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import com.voicesupport.billing.infrastructure.fixtures.EirB2cSampleFixtures;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

// Golden cross-check (TASK-BE-064): parsing a PDF built from a mock invoice must yield the SAME
// business data as the mock fixture it came from. This is a SEMANTIC round-trip, not a real-layout
// test: the raw anonymized eir B2C PDFs are held outside the repo (eir-b2c-invoice-samples.md), so each
// fixture invoice is rendered to a real PDF via the labeled grammar, then re-parsed by the real
// PdfBoxInvoiceExtractorAdapter. We assert business equivalence (invoice id, account, period, TTC/HT/VAT
// totals, and per-line category + TTC amount) — NOT provenance (Evidence.source legitimately becomes
// "pdfbox"), the section/group tree, the per-line periods, nor the per-line VAT split (the grammar
// carries one amount per line + a global VAT). Proving the parser reproduces the fixtures from the real
// eir PDF layout needs those PDF bytes + a parser tuned to the eir layout (OQ-003, follow-up ticket).
class PdfFixtureEquivalenceTest {

    private final PdfBoxInvoiceExtractorAdapter adapter = new PdfBoxInvoiceExtractorAdapter();

    @Test
    void everySyntheticMockInvoiceRenderedAsPdfReParsesToTheSameBusinessData() throws IOException {
        // GIVEN the six synthetic BSS invoices that feed both the mock and the fixture-PDF sources
        assertAllReParseToTheSameBusinessData(BssBillingFixtures.all());
    }

    @Test
    void everyRealEirB2cTranscribedInvoiceRenderedAsPdfReParsesToTheSameBusinessData() throws IOException {
        // GIVEN the three real billing accounts transcribed from the anonymized eir B2C sample PDFs
        // (99224964 / 99226126 / 99226337), with negative discount lines, proratas and multi-section trees
        assertAllReParseToTheSameBusinessData(EirB2cSampleFixtures.all());
    }

    private void assertAllReParseToTheSameBusinessData(Map<AccountId, List<Invoice>> fixtures) throws IOException {
        for (List<Invoice> invoices : fixtures.values()) {
            for (Invoice expected : invoices) {
                // WHEN the invoice is rendered to a real PDF and re-parsed by the real extractor
                ExtractionResult result = adapter.extract(new PdfSource(expected.id().value(), pdfOf(expected)));

                if (expected.lines().isEmpty()) {
                    // THEN a no-line invoice (the "unusable" fixture) fails closed, matching its mock semantics
                    assertEquals(ExtractionStatus.FAILED, result.status(),
                            "no-line invoice should be unusable: " + expected.id().value());
                    assertFalse(result.hasInvoice(), "unusable invoice must carry no data: " + expected.id().value());
                    continue;
                }

                // THEN a lined invoice re-parses to the same identity, period, totals and line amounts
                assertEquals(ExtractionStatus.SUCCESS, result.status(),
                        "lined invoice should reconcile: " + expected.id().value());
                assertBusinessEquivalent(expected, result.invoice());
            }
        }
    }

    private static void assertBusinessEquivalent(Invoice expected, Invoice parsed) {
        String id = expected.id().value();
        assertEquals(expected.id().value(), parsed.id().value(), "invoice id: " + id);
        assertEquals(expected.accountId().value(), parsed.accountId().value(), "account: " + id);
        assertEquals(expected.period().id(), parsed.period().id(), "period id: " + id);
        assertEquals(expected.period().invoiceDate(), parsed.period().invoiceDate(), "invoice date: " + id);

        assertEquals(expected.totals().taxIncluded().minorUnits(), parsed.totals().taxIncluded().minorUnits(),
                "TTC total: " + id);
        assertEquals(expected.totals().taxExcluded().minorUnits(), parsed.totals().taxExcluded().minorUnits(),
                "HT total: " + id);
        assertEquals(expected.totals().tax().minorUnits(), parsed.totals().tax().minorUnits(), "VAT total: " + id);

        List<InvoiceItem> expectedLines = expected.lines();
        List<InvoiceItem> parsedLines = parsed.lines();
        assertEquals(expectedLines.size(), parsedLines.size(), "line count: " + id);
        for (int i = 0; i < expectedLines.size(); i++) {
            assertEquals(expectedLines.get(i).category(), parsedLines.get(i).category(), "line " + i + " category: " + id);
            assertEquals(expectedLines.get(i).amounts().taxIncluded().minorUnits(),
                    parsedLines.get(i).amounts().taxIncluded().minorUnits(), "line " + i + " TTC: " + id);
        }
    }

    // Renders an invoice into the labeled grammar the parser reads, then writes it as a real PDF.
    private static byte[] pdfOf(Invoice invoice) throws IOException {
        List<String> grammar = new ArrayList<>();
        grammar.add("INVOICE " + invoice.id().value());
        grammar.add("ACCOUNT " + invoice.accountId().value());
        grammar.add("PERIOD " + invoice.period().id());
        grammar.add("DATE " + invoice.period().invoiceDate());
        grammar.add("CURRENCY EUR");
        for (InvoiceItem line : invoice.lines()) {
            grammar.add("LINE " + line.category().name() + "|" + line.category().name()
                    + "|" + euros(line.amounts().taxIncluded().minorUnits()));
        }
        grammar.add("VAT " + euros(invoice.totals().tax().minorUnits()));
        grammar.add("TOTAL " + euros(invoice.totals().taxIncluded().minorUnits()));
        return render(grammar);
    }

    private static String euros(long cents) {
        return BigDecimal.valueOf(cents).movePointLeft(2).toPlainString();
    }

    private static byte[] render(List<String> lines) throws IOException {
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                content.setLeading(16f);
                content.newLineAtOffset(50, 750);
                for (String line : lines) {
                    content.showText(line);
                    content.newLine();
                }
                content.endText();
            }
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            document.save(out);
            return out.toByteArray();
        }
    }
}
