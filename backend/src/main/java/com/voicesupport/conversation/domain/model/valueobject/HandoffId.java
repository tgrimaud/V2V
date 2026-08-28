package com.voicesupport.conversation.domain.model.valueobject;

// Opaque identity of a stored EscalationHandoff (TASK-BE-036 / DEC-013). The only thing that
// crosses the channel boundary (with minimal routing metadata) — the full audited payload stays
// backend-owned and is fetched by this reference. Value is a sanitized, non-blank token.
public record HandoffId(String value) {

    private static final int MAX_LENGTH = 200;

    public HandoffId {
        value = sanitize(value);
        if (value.isBlank()) {
            throw new IllegalArgumentException("handoff id must not be blank");
        }
    }

    public static HandoffId of(String value) {
        return new HandoffId(value);
    }

    // Strips control characters and length-bounds the id: it reaches logs and a path variable, so a
    // crafted value must not be able to forge log lines or bloat the key (same stance as CorrelationId).
    private static String sanitize(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("handoff id must not be null");
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
