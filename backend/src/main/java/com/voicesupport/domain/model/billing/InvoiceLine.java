package com.voicesupport.domain.model.billing;

import java.util.List;
import java.util.Objects;

public record InvoiceLine(
        String id,
        String label,
        InvoiceLineCategory category,
        Money amount,
        List<Evidence> evidence
) {

    public InvoiceLine {
        requireText(id, "line id required");
        requireText(label, "line label required");
        Objects.requireNonNull(category, "line category required");
        Objects.requireNonNull(amount, "line amount required");
        evidence = List.copyOf(Objects.requireNonNull(evidence, "line evidence required"));
        if (evidence.isEmpty()) {
            throw new IllegalArgumentException("line evidence required");
        }
    }

    public String comparisonKey() {
        return category + "::" + label.strip().toLowerCase();
    }

    private static void requireText(String value, String message) {
        Objects.requireNonNull(value, message);
        if (value.isBlank()) {
            throw new IllegalArgumentException(message);
        }
    }
}
