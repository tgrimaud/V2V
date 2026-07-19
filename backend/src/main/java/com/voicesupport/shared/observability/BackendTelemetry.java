package com.voicesupport.shared.observability;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.function.Supplier;

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

    private final MeterRegistry registry;

    public BackendTelemetry(MeterRegistry registry) {
        this.registry = registry;
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
        String channel = CorrelationId.currentChannel();
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
}
