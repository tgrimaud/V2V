package com.voicesupport.billing.domain.model;

// The business reason a set of line deltas is attributed to. UNEXPLAINED is the fail-closed bucket
// for a delta the deterministic engine cannot attribute — it is surfaced (never hidden) and can
// gate the explanation or trigger escalation (BR-003, ADR-0019). SERVICE_ADDED / SERVICE_REMOVED cover
// a subscription line that appeared / disappeared (a new or removed service), distinct from an opaque
// in-place subscription change which stays UNEXPLAINED (TASK-BE-067).
public enum BillingCauseType {
    DISCOUNT_EXPIRY,
    USAGE_OVERAGE,
    OPTION_CHANGE,
    SERVICE_ADDED,
    SERVICE_REMOVED,
    PRORATION,
    TAX,
    ONE_OFF_FEE,
    ADJUSTMENT,
    UNEXPLAINED
}
