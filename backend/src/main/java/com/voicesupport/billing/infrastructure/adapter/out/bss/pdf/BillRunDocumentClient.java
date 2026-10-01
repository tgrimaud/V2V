package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;

import java.util.List;
import java.util.Optional;

// Thin seam over the Galaxion `bill-run-documents` service (TASK-BE-063): find an invoice document
// then download its PDF bytes. Its own interface so the port adapter depends on a narrow capability
// (not an HTTP client) and the HTTP mapping stays independently swappable + unit-testable through a
// fake. Maps Galaxion GET /bill-run-documents/search and GET /bill-run-documents/{document_id}/download
// (galaxion-billing-contracts.md). The search response carries ONLY id/filename/contentType — no
// period/amount (missing-inputs.md), which is why the port's listDocuments stays blocked (see
// GalaxionBillRunDocumentAdapter). Returns empty on a not-found document; transport failures propagate
// (mapped to a sanitized 503 upstream). DTOs are nested here (off the top level so the adapter.out
// naming convention stays satisfied); @JsonProperty pins the wire names against the global SNAKE_CASE.
public interface BillRunDocumentClient {

    List<BillRunDocument> search(DocumentSearchCriteria criteria, GalaxionUser user);

    Optional<byte[]> download(String documentId, String billPeriodId, GalaxionUser user);

    // Search criteria for GET /bill-run-documents/search. All optional (any single one locates the
    // document); the port adapter supplies accountId + invoiceNumber, which is enough for V1.
    record DocumentSearchCriteria(String billRunAccountId, String accountId, String invoiceNumber,
            String billPeriodId) {

        public static DocumentSearchCriteria byAccountAndInvoice(String accountId, String invoiceNumber) {
            return new DocumentSearchCriteria(null, accountId, invoiceNumber, null);
        }
    }

    // One entry of the GET /bill-run-documents/search response (BillRunDocumentResponse). Only the
    // fields V1 uses are mapped: `id` (the document to download) + descriptive filename/contentType.
    record BillRunDocument(String id, String filename, String contentType) {
    }
}
