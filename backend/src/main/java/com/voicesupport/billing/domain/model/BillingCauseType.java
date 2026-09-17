package com.voicesupport.billing.domain.model;

// The business reason a set of line deltas is attributed to. UNEXPLAINED is the fail-closed bucket
// for a delta the deterministic engine cannot attribute — it is surfaced (never hidden) and can
// gate the explanation or trigger escalation (BR-003, ADR-0019).
public enum BillingCauseType {
    DISCOUNT_EXPIRY,
    USAGE_OVERAGE,
    OPTION_CHANGE,
    PRORATION,
    TAX,
    ONE_OFF_FEE,
    ADJUSTMENT,
    UNEXPLAINED
}
