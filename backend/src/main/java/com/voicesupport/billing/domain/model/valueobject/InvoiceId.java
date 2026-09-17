package com.voicesupport.billing.domain.model.valueobject;

import java.util.Objects;

// Identity of an invoice. A sanitized, non-blank token: it reaches logs and BSS lookups, so it is
// stripped and length-bounded to keep it a safe key (same stance as the conversation HandoffId).
public record InvoiceId(String value) {

    private static final int MAX_LENGTH = 200;

    public InvoiceId {
        value = sanitize(value);
        if (value.isBlank()) {
            throw new IllegalArgumentException("invoice id must not be blank");
        }
    }

    public static InvoiceId of(String value) {
        return new InvoiceId(value);
    }

    private static String sanitize(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("invoice id must not be null");
        }
        String stripped = raw.strip();
        StringBuilder builder = new StringBuilder(Math.min(stripped.length(), MAX_LENGTH));
        for (int i = 0; i < stripped.length() && builder.length() < MAX_LENGTH; i++) {
            char c = stripped.charAt(i);
            if (!Character.isISOControl(c)) {
                builder.append(c);
            }
        }
        return builder.toString();
    }
}
