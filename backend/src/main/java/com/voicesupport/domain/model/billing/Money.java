package com.voicesupport.domain.model.billing;

import java.util.Objects;

public record Money(long cents, String currency) {

    public Money {
        Objects.requireNonNull(currency, "currency required");
        if (currency.isBlank()) {
            throw new IllegalArgumentException("currency required");
        }
    }

    public static Money ofCents(long cents, String currency) {
        return new Money(cents, currency);
    }

    public static Money zero(String currency) {
        return new Money(0, currency);
    }

    public Money plus(Money other) {
        requireSameCurrency(other);
        return new Money(Math.addExact(cents, other.cents), currency);
    }

    public Money minus(Money other) {
        requireSameCurrency(other);
        return new Money(Math.subtractExact(cents, other.cents), currency);
    }

    public boolean isZero() {
        return cents == 0;
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other money required");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("currency mismatch");
        }
    }
}
