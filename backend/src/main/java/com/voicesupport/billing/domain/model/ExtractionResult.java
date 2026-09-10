package com.voicesupport.billing.domain.model;

import java.util.List;
import java.util.Objects;

// Result of a PDF extraction (TASK-BE-041, ADR-0005): the status, the structured invoice when one
// could be extracted (null on FAILED), and the human-readable issues that explain a PARTIAL/FAILED
// outcome. The extraction status is first-class so the answer/confidence layer never treats a
// partial or failed extraction as a complete one (BR-003).
public record ExtractionResult(ExtractionStatus status, Invoice invoice, List<String> issues) {

    public ExtractionResult {
        Objects.requireNonNull(status, "status must not be null");
        issues = List.copyOf(Objects.requireNonNull(issues, "issues must not be null"));
        if (status == ExtractionStatus.FAILED && invoice != null) {
            throw new IllegalArgumentException("a FAILED extraction must not carry an invoice");
        }
        if (status != ExtractionStatus.FAILED && invoice == null) {
            throw new IllegalArgumentException("a " + status + " extraction must carry an invoice");
        }
    }

    public static ExtractionResult success(Invoice invoice) {
        return new ExtractionResult(ExtractionStatus.SUCCESS, invoice, List.of());
    }

    public static ExtractionResult partial(Invoice invoice, List<String> issues) {
        return new ExtractionResult(ExtractionStatus.PARTIAL, invoice, issues);
    }

    public static ExtractionResult failed(String reason) {
        return new ExtractionResult(ExtractionStatus.FAILED, null, List.of(reason));
    }

    public boolean hasInvoice() {
        return invoice != null;
    }
}
