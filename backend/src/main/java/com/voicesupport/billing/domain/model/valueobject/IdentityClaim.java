package com.voicesupport.billing.domain.model.valueobject;

import java.util.Objects;

// A claimed customer identity from a channel (TASK-BE-044, ADR-0050): the channel it came from and a
// reference the customer provided (account reference, ANI...). It is a *claim*, not proof — the
// directory + fail-closed resolution decide whether it grants billing access. The reference is
// potentially personal data and must never be logged in clear.
public record IdentityClaim(String channel, String reference) {

    public IdentityClaim {
        channel = sanitize(channel, "channel");
        reference = sanitize(reference, "reference");
    }

    private static String sanitize(String value, String field) {
        Objects.requireNonNull(value, field + " must not be null");
        String stripped = value.strip();
        if (stripped.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return stripped;
    }
}
