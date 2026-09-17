package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.ExplanationConfidence;
import com.voicesupport.billing.domain.model.ExplanationReadiness;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceComparison;
import com.voicesupport.billing.domain.model.ReadinessReason;
import com.voicesupport.billing.domain.port.in.AssessComparisonReadinessUseCase;

import java.util.Objects;

// Evidence-sufficiency / confidence gate (TASK-BE-043). Given a deterministic comparison it decides
// whether the result is safe to explain (DEC-002). Rules, in order:
//   1. neither invoice has a usable billed line               -> INSUFFICIENT / escalate;
//   2. the residual the causes do not account for is zero     -> EXPLAINABLE;
//   3. the residual is within maxResidualRatio of the total   -> PARTIAL (phrase with a caveat);
//   4. otherwise                                              -> INSUFFICIENT / escalate.
// The ratio is provisional pending OQ-002. The residual itself is always surfaced (BR-003), never
// hidden, so escalation and QA carry a traceable amount.
public class ComparisonConfidenceService implements AssessComparisonReadinessUseCase {

    private final double maxResidualRatio;

    public ComparisonConfidenceService(double maxResidualRatio) {
        if (maxResidualRatio < 0.0 || !Double.isFinite(maxResidualRatio)) {
            throw new IllegalArgumentException("maxResidualRatio must be a finite value >= 0");
        }
        this.maxResidualRatio = maxResidualRatio;
    }

    @Override
    public ExplanationReadiness assess(InvoiceComparison comparison) {
        Objects.requireNonNull(comparison, "comparison must not be null");
        if (hasNoUsableLines(comparison)) {
            return verdict(comparison, ExplanationConfidence.INSUFFICIENT, ReadinessReason.NO_USABLE_LINES, true);
        }
        if (comparison.unexplainedAmount().isZero()) {
            return verdict(comparison, ExplanationConfidence.EXPLAINABLE, ReadinessReason.FULLY_EXPLAINED, false);
        }
        if (withinTolerance(comparison)) {
            return verdict(comparison, ExplanationConfidence.PARTIAL, ReadinessReason.PARTIAL_RESIDUAL, false);
        }
        return verdict(comparison, ExplanationConfidence.INSUFFICIENT, ReadinessReason.RESIDUAL_TOO_HIGH, true);
    }

    private static boolean hasNoUsableLines(InvoiceComparison comparison) {
        return isEmpty(comparison.previous()) && isEmpty(comparison.current());
    }

    private static boolean isEmpty(Invoice invoice) {
        return invoice.lines().isEmpty();
    }

    private boolean withinTolerance(InvoiceComparison comparison) {
        long residual = Math.abs(comparison.unexplainedAmount().minorUnits());
        long total = Math.abs(comparison.totalDelta().minorUnits());
        return residual <= Math.round(maxResidualRatio * total);
    }

    private static ExplanationReadiness verdict(InvoiceComparison comparison, ExplanationConfidence confidence,
            ReadinessReason reason, boolean escalate) {
        return new ExplanationReadiness(confidence, reason, escalate, comparison.unexplainedAmount());
    }
}
