package com.voicesupport.domain.model.billing;

import java.util.List;
import java.util.Objects;

public record InvoiceComparison(
        String previousInvoiceNumber,
        String currentInvoiceNumber,
        InvoiceComparisonDecision decision,
        Money totalDelta,
        List<LineDelta> lineDeltas
) {

    public InvoiceComparison {
        Objects.requireNonNull(previousInvoiceNumber, "previous invoice number required");
        Objects.requireNonNull(currentInvoiceNumber, "current invoice number required");
        Objects.requireNonNull(decision, "comparison decision required");
        Objects.requireNonNull(totalDelta, "total delta required");
        lineDeltas = List.copyOf(Objects.requireNonNull(lineDeltas, "line deltas required"));
    }

    public boolean allowed() {
        return decision != InvoiceComparisonDecision.FORBIDDEN;
    }
}
