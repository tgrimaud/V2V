package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.Money;

import java.util.List;
import java.util.Objects;

// A business cause grouping the line deltas that explain part of the total change, with its net
// impact (sum of the grouped contributions, tax-included). The deltas list is defensively copied so
// the cause is immutable.
public record BillingCause(BillingCauseType type, Money impact, List<LineDelta> deltas) {

    public BillingCause {
        Objects.requireNonNull(type, "type must not be null");
        Objects.requireNonNull(impact, "impact must not be null");
        deltas = List.copyOf(Objects.requireNonNull(deltas, "deltas must not be null"));
    }
}
