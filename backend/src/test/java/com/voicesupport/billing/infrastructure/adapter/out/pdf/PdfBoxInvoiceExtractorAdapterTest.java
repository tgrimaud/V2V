package com.voicesupport.billing.infrastructure.adapter.out.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.ExtractionStatus;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PdfBoxInvoiceExtractorAdapterTest {

    private final PdfBoxInvoiceExtractorAdapter adapter = new PdfBoxInvoiceExtractorAdapter();

    @Test
    void extract_realPdfCarryingTheGrammar_roundTripsToASuccessInvoice() throws IOException {
        // GIVEN a real PDF written with PDFBox carrying the labeled invoice grammar
        byte[] pdf = pdfOf(List.of(
                "INVOICE 113444",
                "ACCOUNT 99224964",
                "PERIOD 202608",
                "DATE 2026-08-01",
                "LINE SUBSCRIPTION|Mobile plan|39,99",
                "LINE OPTION|Extra data|5,00",
                "VAT 8,40",
                "TOTAL 44,99"));

        // WHEN the adapter extracts it (real PDFBox text layer + parser)
        ExtractionResult result = adapter.extract(new PdfSource("doc-uuid-1", pdf));

        // THEN the invoice round-trips with its identity and reconciled total
        assertEquals(ExtractionStatus.SUCCESS, result.status());
        assertEquals("113444", result.invoice().id().value());
        assertEquals(4499L, result.invoice().totals().taxIncluded().minorUnits());
        assertEquals(2, result.invoice().lines().size());
    }

    @Test
    void extract_emptyDocument_failsClosed() {
        // GIVEN an empty document (no bytes)
        // WHEN extracted THEN it fails closed without throwing
        ExtractionResult result = adapter.extract(new PdfSource("doc-uuid-2", new byte[0]));
        assertEquals(ExtractionStatus.FAILED, result.status());
        assertFalse(result.hasInvoice());
        assertTrue(result.issues().get(0).contains("empty"));
    }

    @Test
    void extract_corruptBytes_failsClosedWithoutLeakingContent() {
        // GIVEN bytes that are not a valid PDF
        byte[] notAPdf = "this is not a pdf".getBytes(StandardCharsets.UTF_8);

        // WHEN extracted THEN it fails closed, naming only the reference + error type (no content)
        ExtractionResult result = adapter.extract(new PdfSource("doc-uuid-3", notAPdf));
        assertEquals(ExtractionStatus.FAILED, result.status());
        assertTrue(result.issues().get(0).contains("doc-uuid-3"));
        assertFalse(result.issues().get(0).contains("this is not a pdf"));
    }

    private static byte[] pdfOf(List<String> lines) throws IOException {
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
