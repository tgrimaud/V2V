package com.voicesupport.billing.domain.model.valueobject;

import java.util.Currency;
import java.util.Objects;

// Monetary amount as integer minor units (e.g. cents) in a single currency. Amounts are the core of
// billing correctness, so the domain never uses double or a bare long: arithmetic is exact (overflow
// fails fast) and cross-currency operations are rejected. Adapters convert the BSS unit at the
// boundary; invoice-extraction-json.md fixes integer minor units, and the euros-vs-cents question is
// tracked on OQ-003 (INFRA-017).
public record Money(long minorUnits, Currency currency) {

    public Money {
        Objects.requireNonNull(currency, "currency must not be null");
    }

    public static Money ofMinorUnits(long minorUnits, Currency currency) {
        return new Money(minorUnits, currency);
    }

    public static Money zero(Currency currency) {
        return new Money(0L, currency);
    }

    public Money plus(Money other) {
        requireSameCurrency(other);
        return new Money(Math.addExact(minorUnits, other.minorUnits), currency);
    }

    public Money minus(Money other) {
        requireSameCurrency(other);
        return new Money(Math.subtractExact(minorUnits, other.minorUnits), currency);
    }

    public Money negate() {
        return new Money(Math.negateExact(minorUnits), currency);
    }

    public Money abs() {
        return minorUnits < 0L ? negate() : this;
    }

    public boolean isZero() {
        return minorUnits == 0L;
    }

    public boolean isNegative() {
        return minorUnits < 0L;
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other must not be null");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "cannot operate on different currencies: " + currency + " vs " + other.currency);
        }
    }
}
