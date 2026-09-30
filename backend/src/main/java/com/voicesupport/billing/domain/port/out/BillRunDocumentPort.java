package com.voicesupport.billing.domain.port.out;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;

import java.util.List;
import java.util.Optional;

// Read-only access to invoice bill-run documents (the PDF evidence path, ADR-0005): list the
// documents available for an account and download one document's PDF bytes. This is the "fetch" half
// of the PDF-backed BssBillingPort adapter (PdfBssBillingAdapter); turning the downloaded bytes into
// the domain invoice is InvoicePdfExtractorPort's job, so the two concerns stay separable. Every call
// is account-scoped (BR-002-1). Maps to Galaxion GET /bill-run-documents/search and
// GET /bill-run-documents/{document_id}/download; a fixture adapter stands in until real access is
// validated (OQ-003).
public interface BillRunDocumentPort {

    List<InvoiceSummary> listDocuments(AccountId account);

    Optional<PdfSource> download(AccountId account, InvoiceId invoiceId);
}
