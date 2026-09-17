package com.voicesupport.billing.infrastructure.adapter.out.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.domain.port.out.InvoicePdfExtractorPort;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

// Synthetic PDF extractor (TASK-BE-041) exercising the ADR-0005 fallback contract without a real PDF
// parser: it maps a document reference (the fixture invoice's period id) to a structured invoice and
// models the three outcomes. A reference suffixed "-partial" yields a PARTIAL extraction; an empty
// document or an unknown reference yields FAILED. The real PDFBox extractor is deferred until real
// PDFs are provided (mirrors the real BssBillingPort adapter, TASK-BE-047).
public class FixtureInvoicePdfExtractorAdapter implements InvoicePdfExtractorPort {

    private static final String PARTIAL_SUFFIX = "-partial";

    private final Map<String, Invoice> invoicesByReference;

    public FixtureInvoicePdfExtractorAdapter(Map<AccountId, List<Invoice>> fixtures) {
        Objects.requireNonNull(fixtures, "fixtures must not be null");
        this.invoicesByReference = index(fixtures);
    }

    @Override
    public ExtractionResult extract(PdfSource source) {
        Objects.requireNonNull(source, "source must not be null");
        if (source.isEmpty()) {
            return ExtractionResult.failed("empty document: " + source.reference());
        }
        String reference = source.reference();
        if (reference.endsWith(PARTIAL_SUFFIX)) {
            return partial(reference);
        }
        Invoice invoice = invoicesByReference.get(reference);
        if (invoice == null) {
            return ExtractionResult.failed("unreadable document: " + reference);
        }
        return ExtractionResult.success(invoice);
    }

    private ExtractionResult partial(String reference) {
        String base = reference.substring(0, reference.length() - PARTIAL_SUFFIX.length());
        Invoice invoice = invoicesByReference.get(base);
        if (invoice == null) {
            return ExtractionResult.failed("unreadable document: " + reference);
        }
        return ExtractionResult.partial(invoice,
                List.of("some invoice lines could not be extracted from the PDF"));
    }

    private static Map<String, Invoice> index(Map<AccountId, List<Invoice>> fixtures) {
        Map<String, Invoice> byReference = new LinkedHashMap<>();
        for (List<Invoice> invoices : fixtures.values()) {
            for (Invoice invoice : invoices) {
                byReference.putIfAbsent(invoice.period().id(), invoice);
            }
        }
        return byReference;
    }
}
