package com.voicesupport.billing.infrastructure.adapter.out.bss.eir;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;

import java.util.List;

// Thin seam over the Eir billing-service (account invoice list; PDF/CSV reports are a later
// extraction path). Its own interface so the adapter depends on a narrow capability and each Eir
// service stays independently swappable. Returns an empty list when the account has no invoices or is
// not found; transport failures propagate (mapped to a sanitized 503 upstream). The response DTO is
// nested (off the top level for the adapter.out naming convention); @JsonProperty pins the wire names.
public interface BillingServiceClient {

    List<InvoiceHistory> listAccountInvoices(String accountId, GalaxionUser user);

    record InvoiceHistory(
            @JsonProperty("invoiceNumber") Long invoiceNumber,
            @JsonProperty("amount") Long amount,
            @JsonProperty("invoiceDate") String invoiceDate,
            @JsonProperty("dueDate") String dueDate) {
    }
}
