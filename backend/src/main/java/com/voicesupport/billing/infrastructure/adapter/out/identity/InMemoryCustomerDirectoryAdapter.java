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
        Map<String, List<AccountId>> directory = new java.util.LinkedHashMap<>();
        directory.put("EIR-1001", List.of(AccountId.of("eir-001")));
        directory.put("EIR-1002", List.of(AccountId.of("eir-002")));
        directory.put("EIR-1003", List.of(AccountId.of("eir-003")));
        directory.put("EIR-1004", List.of(AccountId.of("eir-004")));
        directory.put("EIR-1005", List.of(AccountId.of("eir-005")));
        directory.put("EIR-1006", List.of(AccountId.of("eir-006")));
        directory.put("EIR-DUP", List.of(AccountId.of("eir-001"), AccountId.of("eir-002")));
        // Real eir B2C samples (TASK-BE-059): the customer identifies by the billing account number.
        directory.put("99224964", List.of(AccountId.of("99224964")));
        directory.put("99226126", List.of(AccountId.of("99226126")));
        directory.put("99226337", List.of(AccountId.of("99226337")));
        return Map.copyOf(directory);
    }
}
