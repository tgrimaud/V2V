package com.voicesupport.billing.domain.model;

// Why the comparison reached its confidence level (TASK-BE-043) — kept explicit so the answer engine
// and QA can branch deterministically and so escalation carries a traceable reason.
public enum ReadinessReason {
    FULLY_EXPLAINED,
    PARTIAL_RESIDUAL,
    RESIDUAL_TOO_HIGH,
    NO_USABLE_LINES
}
