package com.voicesupport.billing.domain.model;

// Outcome of extracting a structured invoice from a PDF (TASK-BE-041, ADR-0005). SUCCESS: a complete
// invoice was extracted. PARTIAL: an invoice was extracted but some content is missing (surfaced as
// issues) -> downstream must treat confidence accordingly. FAILED: nothing usable could be extracted.
public enum ExtractionStatus {
    SUCCESS,
    PARTIAL,
    FAILED
}
