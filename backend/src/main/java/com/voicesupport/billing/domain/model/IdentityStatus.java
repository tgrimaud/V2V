package com.voicesupport.billing.domain.model;

// Outcome of resolving a customer identity claim (TASK-BE-044, ADR-0050). RESOLVED: exactly one
// matching account -> billing access granted. UNRESOLVED: no match. AMBIGUOUS: more than one match.
// Only RESOLVED grants billing access (fail-closed, BR-002-1); the other two never yield an account.
public enum IdentityStatus {
    RESOLVED,
    UNRESOLVED,
    AMBIGUOUS
}
