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

    private CorrelationId() {
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
        if (value != null && !value.isBlank()) {
            MDC.put(MDC_KEY, value);
        }
    }

    public static void setChannel(String value) {
        MDC.put(CHANNEL_MDC_KEY, value == null || value.isBlank() ? NONE : value);
    }

    public static void clearChannel() {
        MDC.remove(CHANNEL_MDC_KEY);
    }
}
