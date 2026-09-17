package com.voicesupport.billing.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Currency;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("LineAmounts (tax-included / tax-excluded / tax)")
class LineAmountsTest {

    private static final Currency EUR = Currency.getInstance("EUR");
    private static final Currency USD = Currency.getInstance("USD");

    @Test
    void builds_when_all_three_amounts_share_a_currency() {
        // GIVEN three euro amounts
        Money incl = Money.ofMinorUnits(1200L, EUR);
        Money excl = Money.ofMinorUnits(1000L, EUR);
        Money tax = Money.ofMinorUnits(200L, EUR);

        // WHEN a LineAmounts is built
        LineAmounts amounts = new LineAmounts(incl, excl, tax);

        // THEN the tax-included amount is the customer-facing basis
        assertThat(amounts.taxIncluded().minorUnits()).isEqualTo(1200L);
    }

    @Test
    void throws_when_currencies_differ() {
        // GIVEN amounts in mixed currencies
        Money incl = Money.ofMinorUnits(1200L, EUR);
        Money excl = Money.ofMinorUnits(1000L, USD);
        Money tax = Money.ofMinorUnits(200L, EUR);

        // WHEN / THEN construction is rejected
        assertThatThrownBy(() -> new LineAmounts(incl, excl, tax))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("single currency");
    }

    @Test
    void throws_when_any_amount_is_null() {
        // GIVEN a null tax amount
        Money incl = Money.ofMinorUnits(1200L, EUR);
        Money excl = Money.ofMinorUnits(1000L, EUR);

        // WHEN / THEN construction is rejected
        assertThatThrownBy(() -> new LineAmounts(incl, excl, null))
                .isInstanceOf(NullPointerException.class);
    }
}
