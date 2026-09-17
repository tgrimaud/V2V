package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.AccountId;

import java.util.Objects;

// The verdict of identity resolution (TASK-BE-044, ADR-0050): the status and, only when RESOLVED, the
// billing account it grants access to. Fail-closed by construction (BR-002-1): a non-RESOLVED verdict
// carries no account, so a caller can never obtain an account without an unambiguous match.
public record IdentityResolution(IdentityStatus status, AccountId account) {

    public IdentityResolution {
        Objects.requireNonNull(status, "status must not be null");
        if (status == IdentityStatus.RESOLVED && account == null) {
            throw new IllegalArgumentException("a RESOLVED identity must carry an account");
        }
        if (status != IdentityStatus.RESOLVED && account != null) {
            throw new IllegalArgumentException("a " + status + " identity must not carry an account");
        }
    }

    public static IdentityResolution resolved(AccountId account) {
        return new IdentityResolution(IdentityStatus.RESOLVED, account);
    }

    public static IdentityResolution unresolved() {
        return new IdentityResolution(IdentityStatus.UNRESOLVED, null);
    }

    public static IdentityResolution ambiguous() {
        return new IdentityResolution(IdentityStatus.AMBIGUOUS, null);
    }

    public boolean canAccessBilling() {
        return status == IdentityStatus.RESOLVED;
    }
}
