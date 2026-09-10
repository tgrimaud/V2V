package com.voicesupport.billing.domain.model.valueobject;

import java.util.Objects;

// A source invoice PDF to extract (TASK-BE-041, ADR-0005): a document reference plus its raw bytes.
// The byte array is defensively copied in and out so the value object stays immutable. This is the
// fallback path — structured BSS (GET /invoices/composed) is primary when reachable read-only.
public record PdfSource(String reference, byte[] content) {

    public PdfSource {
        Objects.requireNonNull(reference, "reference must not be null");
        if (reference.isBlank()) {
            throw new IllegalArgumentException("reference must not be blank");
        }
        reference = reference.strip();
        content = Objects.requireNonNull(content, "content must not be null").clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }

    public boolean isEmpty() {
        return content.length == 0;
    }
}
