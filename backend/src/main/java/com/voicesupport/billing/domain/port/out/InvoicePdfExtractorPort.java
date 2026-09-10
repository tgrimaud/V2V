package com.voicesupport.billing.domain.port.out;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;

// Outbound port for deterministic invoice-PDF extraction (TASK-BE-041, ADR-0005): the fallback used
// when the structured BSS source is not reachable. Implementations parse the PDF into the domain
// invoice model before any comparison; the LLM never reads the PDF. Synthetic fixture adapter now;
// the real parser (e.g. PDFBox) registers later once real PDFs are available.
public interface InvoicePdfExtractorPort {

    ExtractionResult extract(PdfSource source);
}
