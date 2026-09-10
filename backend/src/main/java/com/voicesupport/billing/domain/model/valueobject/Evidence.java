package com.voicesupport.billing.domain.model.valueobject;

import java.util.Objects;

// Traceable evidence backing a billed line: which source produced it (a structured billing-api line
// or an extracted PDF) and the raw reference/text kept for audit. Every confirmed line must carry
// evidence so the explanation stays traceable and the LLM only phrases proven facts (ADR-0005,
// BR-003-1). documentReference and text may be absent for a structured-source line with no document.
public record Evidence(String source, String documentReference, String text) {

    public Evidence {
        Objects.requireNonNull(source, "evidence source must not be null");
        source = source.strip();
        if (source.isBlank()) {
            throw new IllegalArgumentException("evidence source must not be blank");
        }
    }
}
