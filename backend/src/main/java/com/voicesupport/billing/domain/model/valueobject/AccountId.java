package com.voicesupport.billing.domain.model.valueobject;

// Identity of the billed customer account. Sanitized, non-blank token: it scopes every billing
// lookup, so a customer can only ever be shown their own account (BR-002-1).
public record AccountId(String value) {

    private static final int MAX_LENGTH = 200;

    public AccountId {
        value = sanitize(value);
        if (value.isBlank()) {
            throw new IllegalArgumentException("account id must not be blank");
        }
    }

    public static AccountId of(String value) {
        return new AccountId(value);
    }

    private static String sanitize(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("account id must not be null");
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
