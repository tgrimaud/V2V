package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.IdentityResolution;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.IdentityClaim;
import com.voicesupport.billing.domain.port.in.ResolveCustomerIdentityUseCase;
import com.voicesupport.billing.domain.port.out.CustomerDirectoryPort;

import java.util.List;
import java.util.Objects;

// Fail-closed identity resolution (TASK-BE-044, ADR-0050, BR-002-1). Maps directory matches to a
// verdict: exactly one match -> RESOLVED (billing access), no match -> UNRESOLVED, several matches ->
// AMBIGUOUS. A non-single match never yields an account, so a caller can never reach billing without
// an unambiguous identity.
public class CustomerIdentityService implements ResolveCustomerIdentityUseCase {

    private final CustomerDirectoryPort directory;

    public CustomerIdentityService(CustomerDirectoryPort directory) {
        this.directory = Objects.requireNonNull(directory, "directory must not be null");
    }

    @Override
    public IdentityResolution resolve(IdentityClaim claim) {
        Objects.requireNonNull(claim, "claim must not be null");
        List<AccountId> matches = directory.lookup(claim);
        if (matches.isEmpty()) {
            return IdentityResolution.unresolved();
        }
        if (matches.size() > 1) {
            return IdentityResolution.ambiguous();
        }
        return IdentityResolution.resolved(matches.iterator().next());
    }
}
