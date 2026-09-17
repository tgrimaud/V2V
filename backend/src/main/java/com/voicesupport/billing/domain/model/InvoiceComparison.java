package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.Money;

import java.util.List;
import java.util.Objects;

// The deterministic comparison of two invoices (TASK-BE-042 output): the total delta, every line
// delta, the attributed business causes, and the unexplainedAmount that no cause accounts for. The
// unexplainedAmount is a first-class field so a partial explanation is always visible and never
// silently dropped (BR-003, ADR-0019). Delta and cause lists are defensively copied.
public record InvoiceComparison(Invoice previous, Invoice current, Money totalDelta,
        List<LineDelta> lineDeltas, List<BillingCause> causes, Money unexplainedAmount) {

    public InvoiceComparison {
        Objects.requireNonNull(previous, "previous invoice must not be null");
        Objects.requireNonNull(current, "current invoice must not be null");
        Objects.requireNonNull(totalDelta, "totalDelta must not be null");
        Objects.requireNonNull(unexplainedAmount, "unexplainedAmount must not be null");
        lineDeltas = List.copyOf(Objects.requireNonNull(lineDeltas, "lineDeltas must not be null"));
        causes = List.copyOf(Objects.requireNonNull(causes, "causes must not be null"));
    }
}
