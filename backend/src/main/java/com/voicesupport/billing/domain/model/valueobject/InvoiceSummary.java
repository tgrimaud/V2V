package com.voicesupport.billing.domain.model.valueobject;

import java.util.Objects;

// A lightweight descriptor of one available invoice: enough to list the comparable invoices for an
// account and pick the two to compare, without fetching the full line tree. Carries the identity,
// the billing period, and the tax-included total (TTC, the customer-facing basis).
public record InvoiceSummary(InvoiceId id, BillingPeriod period, Money totalTaxIncluded) {

    public InvoiceSummary {
        Objects.requireNonNull(id, "id must not be null");
        Objects.requireNonNull(period, "period must not be null");
        Objects.requireNonNull(totalTaxIncluded, "totalTaxIncluded must not be null");
    }
}
