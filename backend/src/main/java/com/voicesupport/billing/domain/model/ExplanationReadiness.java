package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.Money;

import java.util.Objects;

// Verdict of the evidence-sufficiency / confidence gate (TASK-BE-043) over an InvoiceComparison: the
// confidence level, the traceable reason, whether the turn must escalate instead of being answered,
// and the residual amount that carried the decision. The gate never hides a residual (BR-003); it
// decides whether the grounded result is safe for the LLM to phrase (DEC-002).
public record ExplanationReadiness(ExplanationConfidence confidence, ReadinessReason reason,
        boolean escalate, Money unexplainedAmount) {

    public ExplanationReadiness {
        Objects.requireNonNull(confidence, "confidence must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        Objects.requireNonNull(unexplainedAmount, "unexplainedAmount must not be null");
    }
}
