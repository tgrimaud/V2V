package com.voicesupport.billing.domain.model.valueobject;

import java.time.LocalDate;
import java.util.Objects;

// The billing period an invoice belongs to. The BSS model exposes no explicit period entity, so V1
// identifies a period by a stable id (invoice number / bill-run reference) plus the invoice date;
// the exact enumeration of comparable periods for an account is pending Galaxion (OQ-003).
public record BillingPeriod(String id, LocalDate invoiceDate) {

    public BillingPeriod {
        Objects.requireNonNull(id, "period id must not be null");
        id = id.strip();
        if (id.isBlank()) {
            throw new IllegalArgumentException("period id must not be blank");
        }
        Objects.requireNonNull(invoiceDate, "invoiceDate must not be null");
    }
}
