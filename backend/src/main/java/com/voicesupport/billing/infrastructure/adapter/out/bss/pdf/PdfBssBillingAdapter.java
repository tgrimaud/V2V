package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
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

import java.util.List;
import java.util.Objects;
import java.util.Optional;

// PDF-backed BssBillingPort (ADR-0005): a first-class, selectable alternative to the structured JSON
// adapter (EirBssBillingAdapter). It fetches the invoice document via BillRunDocumentPort then parses
// it with InvoicePdfExtractorPort, regenerating the *same* domain Invoice the structured adapter
// returns — so the comparison/confidence/composer chain is unchanged whichever source is selected.
// The LLM never reads the PDF (DEC-002): parsing is deterministic and happens here. Fail-closed: an
// empty download or a FAILED extraction yields Optional.empty (degrades to safe escalation, never a
// 500), and a defense-in-depth ownership check drops an invoice whose account does not match the
// requested one (BR-002-1).
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
        return telemetry.time(Slices.BSS, PROVIDER, () -> downloadAndExtract(account, invoiceId));
    }

    private Optional<Invoice> downloadAndExtract(AccountId account, InvoiceId invoiceId) {
        Optional<PdfSource> pdf = documents.download(account, invoiceId);
        if (pdf.isEmpty()) {
            return Optional.empty();
        }
        ExtractionResult result = extractor.extract(pdf.get());
        if (!result.hasInvoice()) {
            return Optional.empty();
        }
        return Optional.of(result.invoice()).filter(invoice -> invoice.accountId().equals(account));
    }
}
