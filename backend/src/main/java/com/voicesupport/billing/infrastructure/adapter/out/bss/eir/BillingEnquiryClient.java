package com.voicesupport.billing.infrastructure.adapter.out.bss.eir;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Optional;

// Thin seam over the Eir billing-enquiry-service (structured amount breakdown). Its own interface so
// the adapter depends on a narrow capability, not an HTTP client, and each Eir service stays
// independently swappable. Returns empty when the invoice is not found; transport failures propagate
// (mapped to a sanitized 503 upstream). The response DTOs and the authorization context are nested
// here (kept off the top level so the adapter.out naming convention stays satisfied); field names are
// pinned with @JsonProperty so deserialization is immune to the backend's global SNAKE_CASE strategy.
public interface BillingEnquiryClient {

    Optional<InvoiceResponse> fetchInvoice(long invoiceId, GalaxionUser user);

    // BSS authorization context sent as the galaxion-user-type (REGISTERED/PRIVILEGED/SYSTEM) and
    // galaxion-user-identifier headers. In the customer path this must be derived from the resolved
    // identity (BR-002-1); the pilot uses a configured default while derivation is a follow-up.
    record GalaxionUser(String userType, String userIdentifier) {
    }

    record InvoiceResponse(
            @JsonProperty("accountId") Long accountId,
            @JsonProperty("invoiceId") Long invoiceId,
            @JsonProperty("billPeriod") String billPeriod,
            @JsonProperty("billAmount") BillAmount billAmount,
            @JsonProperty("effectiveDate") String effectiveDate) {
    }

    // Category-level amount breakdown, all integer minor units.
    record BillAmount(
            @JsonProperty("invoiceAmount") Long invoiceAmount,
            @JsonProperty("recurringAmount") Long recurringAmount,
            @JsonProperty("oneOffAmount") Long oneOffAmount,
            @JsonProperty("usageAmount") Long usageAmount,
            @JsonProperty("vatAmount") Long vatAmount) {
    }
}
