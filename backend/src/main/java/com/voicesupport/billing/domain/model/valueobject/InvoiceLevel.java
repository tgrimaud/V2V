package com.voicesupport.billing.domain.model.valueobject;

// Level an invoice is issued at, mirroring the BSS `invoice.invoice_level` discriminator: the same
// invoice root is linked either to a billing-account header or to a per-subscription header
// (bss-billing-data-model.md).
public enum InvoiceLevel {
    BILLING_ACCOUNT,
    SUBSCRIPTION
}
