package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.ExtractionStatus;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.domain.port.out.BillRunDocumentPort;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.domain.port.out.InvoicePdfExtractorPort;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

// PDF-backed BssBillingPort (ADR-0005): a first-class, selectable alternative to the structured JSON
// adapter (EirBssBillingAdapter). It fetches the invoice document via BillRunDocumentPort then parses
// it with InvoicePdfExtractorPort, regenerating the *same* domain Invoice the structured adapter
// returns — so the comparison/confidence/composer chain is unchanged whichever source is selected.
// The LLM never reads the PDF (DEC-002): parsing is deterministic and happens here. Fail-closed: an
// empty download, a FAILED extraction, or a PARTIAL extraction all yield Optional.empty. PARTIAL is
// fail-closed on purpose (BR-003 / ADR-0005: a partial extraction must never be treated as complete —
// the missing lines could silently skew the comparison), and a defense-in-depth ownership check drops
// an invoice whose account does not match the requested one (BR-002-1). Each fetch records the BSS
// slice with a non-PII `reason` (extraction_failed | extraction_partial | ownership_mismatch |
// document_unavailable) so QA/Ops can measure PDF extraction quality per outcome.
public class PdfBssBillingAdapter implements BssBillingPort {

    private static final String PROVIDER = "pdf";

    private final BillRunDocumentPort documents;
    private final InvoicePdfExtractorPort extractor;
    private final BackendTelemetry telemetry;

    public PdfBssBillingAdapter(BillRunDocumentPort documents, InvoicePdfExtractorPort extractor,
            BackendTelemetry telemetry) {
        this.documents = Objects.requireNonNull(documents, "documents must not be null");
        this.extractor = Objects.requireNonNull(extractor, "extractor must not be null");
        this.telemetry = Objects.requireNonNull(telemetry, "telemetry must not be null");
    }

    @Override
    public List<InvoiceSummary> listInvoices(AccountId account) {
        Objects.requireNonNull(account, "account must not be null");
        return telemetry.time(Slices.BSS, PROVIDER, () -> documents.listDocuments(account));
    }

    @Override
    public Optional<Invoice> fetchInvoice(AccountId account, InvoiceId invoiceId) {
        Objects.requireNonNull(account, "account must not be null");
        Objects.requireNonNull(invoiceId, "invoiceId must not be null");
        long start = System.nanoTime();
        FetchResult result = resolve(account, invoiceId);
        telemetry.recordLatency(Slices.BSS, PROVIDER, result.outcome(), result.reason(),
                Duration.ofNanos(System.nanoTime() - start));
        return result.invoice();
    }

    private FetchResult resolve(AccountId account, InvoiceId invoiceId) {
        Optional<PdfSource> pdf = documents.download(account, invoiceId);
        if (pdf.isEmpty()) {
            return FetchResult.error("document_unavailable");
        }
        return fromExtraction(account, extractor.extract(pdf.get()));
    }

    private FetchResult fromExtraction(AccountId account, ExtractionResult result) {
        if (result.status() == ExtractionStatus.FAILED) {
            return FetchResult.error("extraction_failed");
        }
        if (result.status() == ExtractionStatus.PARTIAL) {
            return FetchResult.error("extraction_partial");
        }
        if (!result.invoice().accountId().equals(account)) {
            return FetchResult.error("ownership_mismatch");
        }
        return FetchResult.success(result.invoice());
    }

    // Carries the resolved invoice (empty on any fail-closed branch) plus the non-PII telemetry
    // outcome/reason so the BSS slice can distinguish why a PDF fetch produced no usable invoice.
    private record FetchResult(Optional<Invoice> invoice, String outcome, String reason) {

        private static final String SUCCESS = "success";
        private static final String ERROR = "error";
        private static final String REASON_NONE = "n/a";

        private static FetchResult success(Invoice invoice) {
            return new FetchResult(Optional.of(invoice), SUCCESS, REASON_NONE);
        }

        private static FetchResult error(String reason) {
            return new FetchResult(Optional.empty(), ERROR, reason);
        }
    }
}
