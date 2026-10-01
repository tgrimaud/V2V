package com.voicesupport.billing.infrastructure.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;

// Seam between the PDFBox text layer and a layout-specific parser (TASK-BE-064/065). The adapter
// (PdfBoxInvoiceExtractorAdapter) extracts the raw text once, then delegates to one of these: the
// generic labeled-grammar InvoiceTextParser (pdf.source=pdfbox) or the real eir B2C layout parser
// EirB2cInvoiceLayoutParser (pdf.source=eir-b2c). Both turn text into the domain ExtractionResult;
// the LLM never reads the PDF (DEC-002).
public interface PdfTextInvoiceParser {

    ExtractionResult parse(String text, String documentReference);
}
