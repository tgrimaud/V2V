package com.voicesupport.billing.infrastructure.adapter.out.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.domain.port.out.InvoicePdfExtractorPort;
import com.voicesupport.billing.infrastructure.pdf.InvoiceTextParser;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;

import java.io.IOException;
import java.util.Objects;

// Real invoice-PDF extractor (TASK-BE-064, ADR-0005) selected via pdf.source=pdfbox. Apache PDFBox
// turns the PDF bytes into text (the real, deterministic PDF layer), then InvoiceTextParser maps that
// text onto the domain Invoice per invoice-extraction-json.md. The LLM never reads the PDF (DEC-002).
// Fail-closed: an empty document, a corrupt/unreadable PDF, or any parsing error yields a FAILED
// ExtractionResult (never a thrown exception), so the PdfBssBillingAdapter degrades to a safe
// escalation rather than a 500. The failure reason carries only the document reference + the error
// type, never PDF content (no PII leak).
public class PdfBoxInvoiceExtractorAdapter implements InvoicePdfExtractorPort {

    private final InvoiceTextParser parser;

    public PdfBoxInvoiceExtractorAdapter() {
        this.parser = new InvoiceTextParser();
    }

    @Override
    public ExtractionResult extract(PdfSource source) {
        Objects.requireNonNull(source, "source must not be null");
        if (source.isEmpty()) {
            return ExtractionResult.failed("empty document: " + source.reference());
        }
        try {
            String text = extractText(source.content());
            return parser.parse(text, source.reference());
        } catch (IOException | RuntimeException error) {
            return ExtractionResult.failed(
                    "unreadable PDF: " + source.reference() + " (" + error.getClass().getSimpleName() + ")");
        }
    }

    private String extractText(byte[] content) throws IOException {
        try (PDDocument document = Loader.loadPDF(content)) {
            return new PDFTextStripper().getText(document);
        }
    }
}
