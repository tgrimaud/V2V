package com.voicesupport.billing.domain.port.out;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.IdentityClaim;

import java.util.List;

// Outbound port to the customer directory (TASK-BE-044, ADR-0050): returns the billing accounts that
// match a claimed identity. It returns the raw matches (0, 1 or many); the domain decides the
// fail-closed verdict. Mock adapter for the pilot; real CRM/BSS directory later behind the same port.
public interface CustomerDirectoryPort {

    List<AccountId> lookup(IdentityClaim claim);
}
