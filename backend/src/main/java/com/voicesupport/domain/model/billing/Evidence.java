package com.voicesupport.domain.model.billing;

import java.util.Objects;

public record Evidence(String source, String reference, String description) {

    public Evidence {
        requireText(source, "source required");
        requireText(reference, "reference required");
        description = Objects.requireNonNullElse(description, "");
    }

    private static void requireText(String value, String message) {
        Objects.requireNonNull(value, message);
        if (value.isBlank()) {
            throw new IllegalArgumentException(message);
        }
    }
}
