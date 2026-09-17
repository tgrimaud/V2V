package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.IdentityResolution;
import com.voicesupport.billing.domain.model.IdentityStatus;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.IdentityClaim;
import com.voicesupport.billing.domain.port.out.CustomerDirectoryPort;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("CustomerIdentityService (fail-closed identity resolution)")
class CustomerIdentityServiceTest {

    private static final IdentityClaim CLAIM = new IdentityClaim("web", "ref-1");

    @Test
    void a_single_match_resolves_and_grants_billing_access() {
        // GIVEN a directory that returns exactly one account
        CustomerIdentityService service = new CustomerIdentityService(
                claim -> List.of(AccountId.of("eir-001")));

        // WHEN the claim is resolved
        IdentityResolution resolution = service.resolve(CLAIM);

        // THEN it is RESOLVED, carries the account, and grants access
        assertThat(resolution.status()).isEqualTo(IdentityStatus.RESOLVED);
        assertThat(resolution.account()).isEqualTo(AccountId.of("eir-001"));
        assertThat(resolution.canAccessBilling()).isTrue();
    }

    @Test
    void no_match_is_unresolved_and_denies_access() {
        // GIVEN a directory that returns no account
        CustomerIdentityService service = new CustomerIdentityService(claim -> List.of());

        // WHEN the claim is resolved
        IdentityResolution resolution = service.resolve(CLAIM);

        // THEN it is UNRESOLVED, carries no account, and denies access (fail-closed)
        assertThat(resolution.status()).isEqualTo(IdentityStatus.UNRESOLVED);
        assertThat(resolution.account()).isNull();
        assertThat(resolution.canAccessBilling()).isFalse();
    }

    @Test
    void several_matches_are_ambiguous_and_deny_access() {
        // GIVEN a directory that returns more than one account
        CustomerIdentityService service = new CustomerIdentityService(
                claim -> List.of(AccountId.of("eir-001"), AccountId.of("eir-002")));

        // WHEN the claim is resolved
        IdentityResolution resolution = service.resolve(CLAIM);

        // THEN it is AMBIGUOUS, carries no account, and denies access (fail-closed)
        assertThat(resolution.status()).isEqualTo(IdentityStatus.AMBIGUOUS);
        assertThat(resolution.account()).isNull();
        assertThat(resolution.canAccessBilling()).isFalse();
    }

    @Test
    void rejects_a_null_claim() {
        // GIVEN a service and WHEN/THEN a null claim is rejected
        CustomerIdentityService service = new CustomerIdentityService(claim -> List.of());
        assertThatThrownBy(() -> service.resolve(null)).isInstanceOf(NullPointerException.class);
    }

    @Test
    void rejects_a_null_directory() {
        // GIVEN / WHEN / THEN a null directory port is rejected at construction
        assertThatThrownBy(() -> new CustomerIdentityService(null))
                .isInstanceOf(NullPointerException.class);
    }
}
