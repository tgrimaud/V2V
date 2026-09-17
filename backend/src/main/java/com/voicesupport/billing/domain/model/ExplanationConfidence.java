package com.voicesupport.billing.domain.model;

// How confidently the deterministic comparison can be explained to the customer (TASK-BE-043).
// EXPLAINABLE: fully reconciled, safe to phrase. PARTIAL: a small residual remains, phrase with a
// caveat. INSUFFICIENT: cannot be trusted or nothing to explain -> withhold and escalate.
public enum ExplanationConfidence {
    EXPLAINABLE,
    PARTIAL,
    INSUFFICIENT
}
