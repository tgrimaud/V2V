package com.voicesupport.billing.infrastructure.adapter.out.identity;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.IdentityClaim;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("InMemoryCustomerDirectoryAdapter (pilot directory)")
class InMemoryCustomerDirectoryAdapterTest {

    private final InMemoryCustomerDirectoryAdapter directory = new InMemoryCustomerDirectoryAdapter();

    @Test
    void maps_a_known_reference_to_a_single_account_case_insensitively() {
        // GIVEN a known reference in mixed case
        IdentityClaim claim = new IdentityClaim("web", "eir-1003");

        // WHEN it is looked up
        // THEN it resolves to the matching account
        assertThat(directory.lookup(claim)).containsExactly(AccountId.of("eir-003"));
    }

    @Test
    void returns_no_match_for_an_unknown_reference() {
        // GIVEN an unknown reference
        IdentityClaim claim = new IdentityClaim("web", "not-a-customer");

        // WHEN / THEN the lookup returns no account (fail-closed upstream)
        assertThat(directory.lookup(claim)).isEmpty();
    }

    @Test
    void returns_several_matches_for_an_ambiguous_reference() {
        // GIVEN the intentionally ambiguous reference
        IdentityClaim claim = new IdentityClaim("web", "eir-dup");

        // WHEN / THEN the lookup returns more than one account (domain resolves to AMBIGUOUS)
        assertThat(directory.lookup(claim))
                .containsExactly(AccountId.of("eir-001"), AccountId.of("eir-002"));
    }
}
