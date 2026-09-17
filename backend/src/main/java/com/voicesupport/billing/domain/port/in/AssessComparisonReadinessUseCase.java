package com.voicesupport.billing.domain.port.in;

import com.voicesupport.billing.domain.model.ExplanationReadiness;
import com.voicesupport.billing.domain.model.InvoiceComparison;

// Inbound use case (TASK-BE-043, BR-003, DEC-002): decide whether a deterministic comparison is
// sufficiently reconciled to be explained to the customer, or whether it must be withheld and
// escalated. Thresholds are provisional pending OQ-002.
public interface AssessComparisonReadinessUseCase {

    ExplanationReadiness assess(InvoiceComparison comparison);
}
