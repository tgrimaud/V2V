package com.voicesupport.shared.observability;

import org.slf4j.MDC;

// Shared constants + accessors for the request correlation id (TASK-BE-009). The id lives in
// the SLF4J MDC for the duration of a request so every structured log line (guardrails,
// retrieval, LLM, telemetry) carries the same id, giving runtime -> backend continuity.
public final class CorrelationId {

    public static final String HEADER = "X-Correlation-Id";
    public static final String MDC_KEY = "correlation_id";
    public static final String CHANNEL_MDC_KEY = "channel";
    private static final String NONE = "n/a";
    // Bounds a client-supplied correlation id / channel so a crafted value cannot forge log lines
    // (CR/LF injection) nor bloat the MDC/response header (TASK-BE-022 review #3).
    private static final int MAX_LENGTH = 200;

    private CorrelationId() {
    }

    // Removes ISO control characters (CR/LF/TAB/…) and caps the length of a client-controlled
    // correlation id or channel before it reaches the MDC, a structured log or a response header.
    // Control chars are the log-injection / HTTP response-splitting vector; normal ids (UUIDs,
    // alphanumerics, dashes) pass through unchanged. Returns null for null so callers keep their
    // own blank handling.
    public static String sanitize(String value) {
        if (value == null) {
            return null;
        }
        String stripped = value.strip();
        StringBuilder builder = new StringBuilder(Math.min(stripped.length(), MAX_LENGTH));
        for (int i = 0; i < stripped.length() && builder.length() < MAX_LENGTH; i++) {
            char c = stripped.charAt(i);
            if (!Character.isISOControl(c)) {
                builder.append(c);
            }
        }
        return builder.toString();
    }

    public static String current() {
        String value = MDC.get(MDC_KEY);
        return value == null || value.isBlank() ? NONE : value;
    }

    public static String currentChannel() {
        String value = MDC.get(CHANNEL_MDC_KEY);
        return value == null || value.isBlank() ? NONE : value;
    }

    // Overrides the request correlation id with the authoritative value carried in a request
    // body (e.g. the voice runtime's correlation_id on /converse), so backend logs align with
    // the runtime's id rather than a locally generated one.
    public static void set(String value) {
        String clean = sanitize(value);
        if (clean != null && !clean.isBlank()) {
            MDC.put(MDC_KEY, clean);
        }
    }

    public static void setChannel(String value) {
        String clean = sanitize(value);
        MDC.put(CHANNEL_MDC_KEY, clean == null || clean.isBlank() ? NONE : clean);
    }

    public static void clearChannel() {
        MDC.remove(CHANNEL_MDC_KEY);
    }
}
