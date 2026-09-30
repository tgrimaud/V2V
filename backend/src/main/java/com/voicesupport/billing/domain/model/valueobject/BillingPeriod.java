package com.voicesupport.billing.domain.model.valueobject;

import java.time.LocalDate;
import java.util.Objects;

// The billing period an invoice belongs to. `id` is a stable bill-run reference (invoice number /
// bill-run id) and `invoiceDate` is the issue ("Billing date") kept for audit and display. Two
// optional windows model the real invoice (ADR-0054, eir-b2c-invoice-samples.md): `usagePeriod` is
// the customer-facing "this month" window (the canonical ordering/labeling axis via orderingDate()),
// and `chargePeriod` is the forward window recurring subscriptions are billed in advance for. Both
// ranges are nullable so a partially-extracted invoice, or a source that does not expose them, is
// still representable; ordering falls back to invoiceDate when usagePeriod is absent.
public record BillingPeriod(String id, LocalDate invoiceDate, DateRange usagePeriod, DateRange chargePeriod) {

    public BillingPeriod {
        Objects.requireNonNull(id, "period id must not be null");
        id = id.strip();
        if (id.isBlank()) {
            throw new IllegalArgumentException("period id must not be blank");
        }
        Objects.requireNonNull(invoiceDate, "invoiceDate must not be null");
    }

    // Backward-compatible shorthand: id + issue date only, no explicit windows (usage/charge null).
    public BillingPeriod(String id, LocalDate invoiceDate) {
        this(id, invoiceDate, null, null);
    }

    // The date used to order/compare invoices: the usage-period start when known (the reliable
    // bill-run axis, since the issue date can be identical across bill runs), else the issue date.
    public LocalDate orderingDate() {
        return usagePeriod != null ? usagePeriod.start() : invoiceDate;
    }
}
