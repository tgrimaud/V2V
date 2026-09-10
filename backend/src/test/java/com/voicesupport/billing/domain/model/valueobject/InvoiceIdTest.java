package com.voicesupport.billing.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("InvoiceId (sanitized typed identifier)")
class InvoiceIdTest {

    @Test
    void of_strips_surrounding_whitespace_and_control_characters() {
        // GIVEN a raw value with padding and a control character
        String raw = "  inv-2026-01\t ";

        // WHEN an InvoiceId is built
        InvoiceId id = InvoiceId.of(raw);

        // THEN the value is stripped and control characters are removed
        assertThat(id.value()).isEqualTo("inv-2026-01");
    }

    @Test
    void throws_when_blank() {
        // GIVEN / WHEN / THEN a blank value is rejected
        assertThatThrownBy(() -> InvoiceId.of("   "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("blank");
    }

    @Test
    void throws_when_null() {
        // GIVEN / WHEN / THEN a null value is rejected
        assertThatThrownBy(() -> InvoiceId.of(null))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
