package com.voicesupport.billing.domain.model;

// Outcome of the billing explanation orchestration (TASK-BE-045, ADR-0051). Drives whether the
// answer engine phrases a grounded explanation or escalates fail-closed:
//   EXPLAINED           - fully reconciled, safe to phrase;
//   PARTIALLY_EXPLAINED - phrase with a caveat (a residual remains);
//   IDENTITY_UNRESOLVED - no/ambiguous/missing identity -> ask for a reference, escalate (BR-002-1);
//   NOT_ENOUGH_DATA     - < 2 comparable invoices or INSUFFICIENT readiness -> escalate, no amounts;
//   NOT_A_BILLING_REQUEST - the turn is not a billing-explanation request (intent guard).
public enum BillingExplanationOutcome {
    EXPLAINED,
    PARTIALLY_EXPLAINED,
    IDENTITY_UNRESOLVED,
    NOT_ENOUGH_DATA,
    NOT_A_BILLING_REQUEST
}
