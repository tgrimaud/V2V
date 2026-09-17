package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("IdentityResolution (fail-closed invariants)")
class IdentityResolutionTest {

    @Test
    void a_resolved_verdict_requires_an_account() {
        // GIVEN a RESOLVED status with no account -> WHEN/THEN rejected
        assertThatThrownBy(() -> new IdentityResolution(IdentityStatus.RESOLVED, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void an_unresolved_verdict_must_not_carry_an_account() {
        // GIVEN an UNRESOLVED status with an account -> WHEN/THEN rejected
        assertThatThrownBy(() -> new IdentityResolution(IdentityStatus.UNRESOLVED, AccountId.of("eir-001")))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void factories_build_consistent_verdicts() {
        // GIVEN / WHEN / THEN the factory helpers produce coherent verdicts
        assertThat(IdentityResolution.resolved(AccountId.of("eir-001")).canAccessBilling()).isTrue();
        assertThat(IdentityResolution.unresolved().canAccessBilling()).isFalse();
        assertThat(IdentityResolution.ambiguous().canAccessBilling()).isFalse();
    }
}
