package com.voicesupport.domain.model.billing;

import java.util.Objects;

public record LineDelta(
        String label,
        InvoiceLineCategory category,
        Money previousAmount,
        Money currentAmount,
        Money delta
) {

    public LineDelta {
        Objects.requireNonNull(label, "delta label required");
        Objects.requireNonNull(category, "delta category required");
        Objects.requireNonNull(previousAmount, "previous amount required");
        Objects.requireNonNull(currentAmount, "current amount required");
        Objects.requireNonNull(delta, "delta amount required");
    }
}
