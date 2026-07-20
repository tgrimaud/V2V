package com.voicesupport.shared.observability;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Arrays;
import java.util.Set;
import java.util.function.Supplier;
import java.util.stream.Collectors;

// Per-slice latency instrumentation (TASK-BE-009). Times a unit of work as a Micrometer timer
// (voice_support.slice) tagged by slice/channel/provider/outcome with client-side p50/p95/p99
// percentiles, and emits a privacy-safe [TELEMETRY] structured log carrying the correlation id.
// Tags and logs expose only technical dimensions and durations — never raw transcript, answer
// text or secrets. A Micrometer Tracing OTel bridge can later promote these timings to spans
// without touching call sites (ADR-0028).
@Component
public class BackendTelemetry {

    private static final Logger log = LoggerFactory.getLogger(BackendTelemetry.class);
    private static final String TIMER = "voice_support.slice";
    private static final String OUTCOME_SUCCESS = "success";
    private static final String OUTCOME_ERROR = "error";
    private static final String CHANNEL_NONE = "n/a";
    private static final String CHANNEL_OTHER = "other";
    private static final String DEFAULT_ALLOWED_CHANNELS = "web,phone,whatsapp,api";

    private final MeterRegistry registry;
    // Bounds the `channel` tag to a known allow-list so a client-supplied value cannot explode
    // the metric time-series cardinality (unknown values collapse to `other`); the raw channel
    // stays visible in the [CONVERSE] log for debugging.
    private final Set<String> allowedChannels;

    // Test convenience: default channel allow-list.
    public BackendTelemetry(MeterRegistry registry) {
        this(registry, DEFAULT_ALLOWED_CHANNELS);
    }

    @Autowired
    public BackendTelemetry(
            MeterRegistry registry,
            @Value("${voice-support.observability.allowed-channels:" + DEFAULT_ALLOWED_CHANNELS + "}")
            String allowedChannelsCsv) {
        this.registry = registry;
        this.allowedChannels = Arrays.stream(allowedChannelsCsv.split(","))
                .map(String::trim).map(s -> s.toLowerCase(java.util.Locale.ROOT))
                .filter(s -> !s.isBlank()).collect(Collectors.toUnmodifiableSet());
    }

    public <T> T time(String slice, String provider, Supplier<T> work) {
        long start = System.nanoTime();
        String outcome = OUTCOME_SUCCESS;
        try {
            return work.get();
        } catch (RuntimeException e) {
            outcome = OUTCOME_ERROR;
            throw e;
        } finally {
            record(slice, provider, outcome, System.nanoTime() - start);
        }
    }

    private void record(String slice, String provider, String outcome, long elapsedNanos) {
        String channel = normalizeChannel(CorrelationId.currentChannel());
        String safeProvider = provider == null || provider.isBlank() ? "n/a" : provider;
        Timer.builder(TIMER)
                .tag("slice", slice)
                .tag("channel", channel)
                .tag("provider", safeProvider)
                .tag("outcome", outcome)
                .publishPercentiles(0.5, 0.95, 0.99)
                .register(registry)
                .record(Duration.ofNanos(elapsedNanos));
        log.info("[TELEMETRY] slice={} channel={} provider={} outcome={} correlation_id={} duration_ms={}",
                slice, channel, safeProvider, outcome, CorrelationId.current(), elapsedNanos / 1_000_000);
    }

    private String normalizeChannel(String raw) {
        if (raw == null || raw.isBlank() || CHANNEL_NONE.equalsIgnoreCase(raw.trim())) {
            return CHANNEL_NONE;
        }
        String candidate = raw.trim().toLowerCase(java.util.Locale.ROOT);
        return allowedChannels.contains(candidate) ? candidate : CHANNEL_OTHER;
    }
}
