package com.voicesupport.shared.observability;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@DisplayName("BackendTelemetry (per-slice latency timer)")
class BackendTelemetryTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final BackendTelemetry telemetry = new BackendTelemetry(registry);

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    @Test
    @DisplayName("records a success-tagged timer carrying the current channel and provider")
    void recordsSuccess() {
        // GIVEN a known channel for the current request
        CorrelationId.setChannel("web");

        // WHEN a slice of work is timed
        String result = telemetry.time(Slices.RETRIEVAL, "pgvector", () -> "ok");

        // THEN the work result is returned and a success timer is recorded with the tags
        assertEquals("ok", result);
        Timer timer = registry.find("voice_support.slice")
                .tag("slice", Slices.RETRIEVAL)
                .tag("provider", "pgvector")
                .tag("channel", "web")
                .tag("outcome", "success")
                .timer();
        assertNotNull(timer);
        assertEquals(1, timer.count());
    }

    @Test
    @DisplayName("records an error-tagged timer and rethrows when the work fails")
    void recordsError() {
        // GIVEN a failing unit of work
        RuntimeException boom = new IllegalStateException("boom");

        // WHEN it is timed
        RuntimeException thrown = assertThrows(RuntimeException.class,
                () -> telemetry.time(Slices.LLM_WORDING, "mistral-api", () -> {
                    throw boom;
                }));

        // THEN the original exception propagates and an error timer is recorded
        assertEquals(boom, thrown);
        Timer timer = registry.find("voice_support.slice")
                .tag("slice", Slices.LLM_WORDING)
                .tag("outcome", "error")
                .timer();
        assertNotNull(timer);
        assertEquals(1, timer.count());
    }

    @Test
    @DisplayName("defaults channel and provider to n/a when unknown")
    void defaultsUnknownDimensions() {
        // GIVEN no channel in the MDC and a blank provider
        // WHEN timing a slice
        telemetry.time(Slices.BACKEND_REQUEST, "  ", () -> null);

        // THEN the timer carries n/a placeholders rather than empty tags
        Timer timer = registry.find("voice_support.slice")
                .tag("channel", "n/a")
                .tag("provider", "n/a")
                .timer();
        assertNotNull(timer);
    }

    @Test
    @DisplayName("collapses a client-supplied unknown channel to 'other' to bound tag cardinality")
    void boundsUnknownChannelCardinality() {
        // GIVEN a client-controlled channel outside the allow-list (cardinality-attack shape)
        CorrelationId.setChannel("evil-" + "x".repeat(500));

        // WHEN a slice is timed
        telemetry.time(Slices.BACKEND_REQUEST, "pgvector", () -> "ok");

        // THEN the raw value is not used as a tag; it collapses to the bounded 'other' bucket
        assertNotNull(registry.find("voice_support.slice").tag("channel", "other").timer());
    }

    @Test
    @DisplayName("keeps the web_voice runtime channel first-class (TASK-BE-008)")
    void keepsWebVoiceChannelFirstClass() {
        // GIVEN the web Voice2Voice runtime channel
        CorrelationId.setChannel("web_voice");

        // WHEN a slice is timed
        telemetry.time(Slices.BACKEND_REQUEST, "pgvector", () -> "ok");

        // THEN it is reported under its own tag, not collapsed to 'other'
        assertNotNull(registry.find("voice_support.slice").tag("channel", "web_voice").timer());
    }

    @Test
    @DisplayName("normalizes an allow-listed channel case-insensitively")
    void normalizesAllowedChannelCase() {
        // GIVEN an allow-listed channel supplied in mixed case
        CorrelationId.setChannel("Phone");

        // WHEN a slice is timed
        telemetry.time(Slices.BACKEND_REQUEST, "pgvector", () -> "ok");

        // THEN the tag is the normalized lower-case allow-list value
        assertNotNull(registry.find("voice_support.slice").tag("channel", "phone").timer());
    }
}
