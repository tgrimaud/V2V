package com.voicesupport.billing.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("IdentityClaim (sanitization + validation)")
class IdentityClaimTest {

    @Test
    void strips_surrounding_whitespace() {
        // GIVEN a claim with padded fields
        IdentityClaim claim = new IdentityClaim("  web  ", "  ref-1  ");

        // WHEN / THEN the fields are stripped
        assertThat(claim.channel()).isEqualTo("web");
        assertThat(claim.reference()).isEqualTo("ref-1");
    }

    @Test
    void rejects_a_blank_reference() {
        // GIVEN / WHEN / THEN a blank reference is rejected
        assertThatThrownBy(() -> new IdentityClaim("web", "   "))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejects_a_null_channel() {
        // GIVEN / WHEN / THEN a null channel is rejected
        assertThatThrownBy(() -> new IdentityClaim(null, "ref-1"))
                .isInstanceOf(NullPointerException.class);
    }
}
