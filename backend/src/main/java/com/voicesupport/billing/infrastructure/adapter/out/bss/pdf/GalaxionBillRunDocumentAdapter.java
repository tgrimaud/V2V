package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.domain.port.out.BillRunDocumentPort;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;
import com.voicesupport.billing.infrastructure.adapter.out.bss.pdf.BillRunDocumentClient.BillRunDocument;
import com.voicesupport.billing.infrastructure.adapter.out.bss.pdf.BillRunDocumentClient.DocumentSearchCriteria;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Objects;
import java.util.Optional;

// Real BillRunDocumentPort over Galaxion `bill-run-documents` (TASK-BE-063): the download half of the
// PDF evidence path (ADR-0005). It resolves the invoice document via GET /bill-run-documents/search
// (accountId + invoiceNumber) then downloads its PDF through GET /bill-run-documents/{id}/download,
// handing the bytes to InvoicePdfExtractorPort (parsing stays separate). Pairs with the real PDFBox
// extractor (pdf.source=pdfbox, deferred); until both land this adapter is wired only when a base URL
// is configured (BillingConfig), so the default pdf path keeps using the fixtures — nothing is called
// at runtime yet. The galaxion-user-* authorization uses a configured default (SYSTEM) while identity
// -> header derivation is a follow-up (BR-002-1).
//
// listDocuments is BLOCKED by a contract gap: GET /bill-run-documents/search returns only
// id/filename/contentType — no billing period and no amount (missing-inputs.md), so it cannot build an
// InvoiceSummary (which requires period + tax-included total). It therefore fail-closes to an empty
// list rather than fabricating period/amount; the comparable-invoice listing for source=pdf must come
// from a structured hop (eir) or wait for the search response to carry period/amount (OQ-003).
public class GalaxionBillRunDocumentAdapter implements BillRunDocumentPort {

    private static final Logger log = LoggerFactory.getLogger(GalaxionBillRunDocumentAdapter.class);

    private final BillRunDocumentClient client;
    private final GalaxionUser user;

    public GalaxionBillRunDocumentAdapter(BillRunDocumentClient client, GalaxionUser user) {
        this.client = Objects.requireNonNull(client, "client must not be null");
        this.user = Objects.requireNonNull(user, "user must not be null");
    }

    @Override
    public List<InvoiceSummary> listDocuments(AccountId account) {
        Objects.requireNonNull(account, "account must not be null");
        // Fail-closed: the search response lacks period/amount, so no InvoiceSummary can be built here
        // (missing-inputs.md / OQ-003). Returning empty keeps the comparison engine from inventing data.
        log.debug("[BILLRUN] listDocuments unsupported (search lacks period/amount) — returning empty");
        return List.of();
    }

    @Override
    public Optional<PdfSource> download(AccountId account, InvoiceId invoiceId) {
        Objects.requireNonNull(account, "account must not be null");
        Objects.requireNonNull(invoiceId, "invoiceId must not be null");
        return resolveDocumentId(account, invoiceId)
                .flatMap(documentId -> client.download(documentId, null, user)
                        .filter(bytes -> bytes.length > 0)
                        .map(bytes -> new PdfSource(documentId, bytes)));
    }

    // Searches for the invoice document by account + invoice number and takes the first match. Returns
    // the document id to download, or empty when no usable document is found (fail-closed upstream).
    private Optional<String> resolveDocumentId(AccountId account, InvoiceId invoiceId) {
        DocumentSearchCriteria criteria =
                DocumentSearchCriteria.byAccountAndInvoice(account.value(), invoiceId.value());
        return client.search(criteria, user).stream()
                .map(BillRunDocument::id)
                .filter(id -> id != null && !id.isBlank())
                .findFirst();
    }
}
