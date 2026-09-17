package com.voicesupport.billing.domain.port.in;

import com.voicesupport.billing.domain.model.BillingExplanation;
import com.voicesupport.billing.domain.model.valueobject.BillingExplanationQuery;

// Inbound use case (TASK-BE-045, ADR-0051): turn a billing-explanation request into a deterministic,
// grounded BillingExplanation, fail-closed. It chains the intent guard, identity resolution
// (BR-002-1), comparable-invoice retrieval, the deterministic comparison and the confidence gate; the
// LLM only rephrases the grounded text (DEC-002) and never computes amounts. Every degraded branch
// (not a billing request, unresolved identity, not enough data, insufficient readiness) returns a safe
// outcome — never a guessed answer.
public interface ExplainBillingUseCase {

    BillingExplanation explain(BillingExplanationQuery query);
}
