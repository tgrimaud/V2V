package com.voicesupport.billing.domain.model.valueobject;

import java.util.Objects;

// The three amounts carried at every invoice level (item / group / section / invoice). The
// customer-facing comparison basis is taxIncluded — prices are tax-included (TTC), confirmed
// 2026-09-09; taxExcluded and tax are kept for audit only. All three share one currency.
public record LineAmounts(Money taxIncluded, Money taxExcluded, Money tax) {

    public LineAmounts {
        Objects.requireNonNull(taxIncluded, "taxIncluded must not be null");
        Objects.requireNonNull(taxExcluded, "taxExcluded must not be null");
        Objects.requireNonNull(tax, "tax must not be null");
        requireSharedCurrency(taxIncluded, taxExcluded, tax);
    }

    private static void requireSharedCurrency(Money taxIncluded, Money taxExcluded, Money tax) {
        if (!taxIncluded.currency().equals(taxExcluded.currency())
                || !taxIncluded.currency().equals(tax.currency())) {
            throw new IllegalArgumentException("line amounts must share a single currency");
        }
    }
}
