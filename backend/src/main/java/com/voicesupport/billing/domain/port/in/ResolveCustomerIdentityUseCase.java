package com.voicesupport.billing.domain.port.in;

import com.voicesupport.billing.domain.model.IdentityResolution;
import com.voicesupport.billing.domain.model.valueobject.IdentityClaim;

// Inbound use case (TASK-BE-044, ADR-0050, BR-002-1): resolve a claimed customer identity to a
// billing account, fail-closed. Only an unambiguous single match grants access; no match or multiple
// matches never yield an account — the caller must then clarify or escalate, never guess.
public interface ResolveCustomerIdentityUseCase {

    IdentityResolution resolve(IdentityClaim claim);
}
