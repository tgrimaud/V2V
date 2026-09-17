package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.Money;

import java.util.Objects;

// A single line-level difference between the two invoices: how the line changed and its signed
// contribution (current - previous, on the tax-included basis) to the total delta. previousAmount
// and currentAmount are the compared amounts (a zero amount represents an absent line).
public record LineDelta(String label, ChangeKind kind, Money previousAmount, Money currentAmount,
        Money contribution) {

    public LineDelta {
        Objects.requireNonNull(label, "label must not be null");
        Objects.requireNonNull(kind, "kind must not be null");
        Objects.requireNonNull(previousAmount, "previousAmount must not be null");
        Objects.requireNonNull(currentAmount, "currentAmount must not be null");
        Objects.requireNonNull(contribution, "contribution must not be null");
    }
}
