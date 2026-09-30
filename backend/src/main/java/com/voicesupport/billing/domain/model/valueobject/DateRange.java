package com.voicesupport.billing.domain.model.valueobject;

import java.time.LocalDate;
import java.util.Objects;

// A closed date interval [start, end] used across the billing domain: the invoice usage / charge
// windows (BillingPeriod) and a per-line applicable period (InvoiceItem / InvoiceGroup), notably for
// proratas ("from 25 Sep until 11 Oct"). Ordering is validated at construction (ADR-0054); the VO is
// shared so the same range shape is reused at every level instead of duplicated start/end fields.
public record DateRange(LocalDate start, LocalDate end) {

    public DateRange {
        Objects.requireNonNull(start, "start must not be null");
        Objects.requireNonNull(end, "end must not be null");
        if (end.isBefore(start)) {
            throw new IllegalArgumentException("date range end must not be before start: " + start + " > " + end);
        }
    }

    public static DateRange of(LocalDate start, LocalDate end) {
        return new DateRange(start, end);
    }
}
