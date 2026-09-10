package com.voicesupport.billing.infrastructure.adapter.out.identity;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.IdentityClaim;
import com.voicesupport.billing.domain.port.out.CustomerDirectoryPort;

import java.util.List;
import java.util.Map;

// Pilot mock directory (TASK-BE-044, ADR-0050) aligned with the customer-eir-* billing fixtures:
// maps a claimed reference to billing accounts. References are matched case-insensitively. Includes
// an intentionally ambiguous reference so the fail-closed AMBIGUOUS path is exercisable. The real
// CRM/BSS directory adapter registers later behind CustomerDirectoryPort.
public class InMemoryCustomerDirectoryAdapter implements CustomerDirectoryPort {

    private final Map<String, List<AccountId>> accountsByReference;

    public InMemoryCustomerDirectoryAdapter() {
        this(defaultDirectory());
    }

    public InMemoryCustomerDirectoryAdapter(Map<String, List<AccountId>> accountsByReference) {
        this.accountsByReference = Map.copyOf(accountsByReference);
    }

    @Override
    public List<AccountId> lookup(IdentityClaim claim) {
        return accountsByReference.getOrDefault(normalize(claim.reference()), List.of());
    }

    private static String normalize(String reference) {
        return reference.strip().toUpperCase();
    }

    private static Map<String, List<AccountId>> defaultDirectory() {
        return Map.of(
                "EIR-1001", List.of(AccountId.of("eir-001")),
                "EIR-1002", List.of(AccountId.of("eir-002")),
                "EIR-1003", List.of(AccountId.of("eir-003")),
                "EIR-1004", List.of(AccountId.of("eir-004")),
                "EIR-1005", List.of(AccountId.of("eir-005")),
                "EIR-1006", List.of(AccountId.of("eir-006")),
                "EIR-DUP", List.of(AccountId.of("eir-001"), AccountId.of("eir-002")));
    }
}
