package com.voicesupport.billing.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Currency;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("Money (billing amount value object)")
class MoneyTest {

    private static final Currency EUR = Currency.getInstance("EUR");
    private static final Currency USD = Currency.getInstance("USD");

    @Test
    void plus_adds_minor_units_of_the_same_currency() {
        // GIVEN two euro amounts
        Money a = Money.ofMinorUnits(1500L, EUR);
        Money b = Money.ofMinorUnits(250L, EUR);

        // WHEN they are added
        Money sum = a.plus(b);

        // THEN the minor units add up in the same currency
        assertThat(sum.minorUnits()).isEqualTo(1750L);
        assertThat(sum.currency()).isEqualTo(EUR);
    }

    @Test
    void minus_subtracts_minor_units_of_the_same_currency() {
        // GIVEN two euro amounts
        Money a = Money.ofMinorUnits(1500L, EUR);
        Money b = Money.ofMinorUnits(250L, EUR);

        // WHEN one is subtracted from the other
        Money difference = a.minus(b);

        // THEN the minor units subtract in the same currency
        assertThat(difference.minorUnits()).isEqualTo(1250L);
    }

    @Test
    void plus_throws_on_a_different_currency() {
        // GIVEN a euro and a dollar amount
        Money euros = Money.ofMinorUnits(1000L, EUR);
        Money dollars = Money.ofMinorUnits(1000L, USD);

        // WHEN / THEN adding across currencies is rejected
        assertThatThrownBy(() -> euros.plus(dollars))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("different currencies");
    }

    @Test
    void minus_throws_on_a_different_currency() {
        // GIVEN a euro and a dollar amount
        Money euros = Money.ofMinorUnits(1000L, EUR);
        Money dollars = Money.ofMinorUnits(1000L, USD);

        // WHEN / THEN subtracting across currencies is rejected
        assertThatThrownBy(() -> euros.minus(dollars))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void negate_flips_the_sign() {
        // GIVEN a positive amount
        Money positive = Money.ofMinorUnits(4200L, EUR);

        // WHEN negated
        Money negated = positive.negate();

        // THEN the sign flips and the currency is preserved
        assertThat(negated.minorUnits()).isEqualTo(-4200L);
        assertThat(negated.currency()).isEqualTo(EUR);
    }

    @Test
    void abs_returns_the_non_negative_magnitude() {
        // GIVEN a negative and a positive amount
        Money negative = Money.ofMinorUnits(-4200L, EUR);
        Money positive = Money.ofMinorUnits(4200L, EUR);

        // WHEN abs is taken
        // THEN both yield the same non-negative magnitude
        assertThat(negative.abs().minorUnits()).isEqualTo(4200L);
        assertThat(positive.abs()).isSameAs(positive);
    }

    @Test
    void is_zero_and_is_negative_reflect_the_amount() {
        // GIVEN zero, positive and negative amounts
        // WHEN / THEN the predicates reflect the sign
        assertThat(Money.zero(EUR).isZero()).isTrue();
        assertThat(Money.ofMinorUnits(1L, EUR).isZero()).isFalse();
        assertThat(Money.ofMinorUnits(-1L, EUR).isNegative()).isTrue();
        assertThat(Money.ofMinorUnits(1L, EUR).isNegative()).isFalse();
    }

    @Test
    void zero_builds_a_zero_amount_in_the_given_currency() {
        // GIVEN nothing
        // WHEN a zero amount is built
        Money zero = Money.zero(USD);

        // THEN it is zero in that currency
        assertThat(zero.minorUnits()).isZero();
        assertThat(zero.currency()).isEqualTo(USD);
    }

    @Test
    void plus_throws_on_overflow() {
        // GIVEN an amount at the long ceiling
        Money max = Money.ofMinorUnits(Long.MAX_VALUE, EUR);
        Money one = Money.ofMinorUnits(1L, EUR);

        // WHEN / THEN overflowing the exact arithmetic fails fast rather than wrapping
        assertThatThrownBy(() -> max.plus(one)).isInstanceOf(ArithmeticException.class);
    }

    @Test
    void currency_must_not_be_null() {
        // GIVEN / WHEN / THEN a null currency is rejected at construction
        assertThatThrownBy(() -> Money.ofMinorUnits(1L, null))
                .isInstanceOf(NullPointerException.class);
    }
}
