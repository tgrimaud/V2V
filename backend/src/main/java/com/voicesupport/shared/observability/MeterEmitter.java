package com.voicesupport.shared.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

// Centralizes the Micrometer builder boilerplate (register on the shared registry + the common
// client-side p50/p95/p99 percentiles) so BackendTelemetry's recordX methods stay focused on tag
// and log semantics. Extracted for the 200-line budget; behaviour is unchanged.
class MeterEmitter {

    private static final double[] PERCENTILES = {0.5, 0.95, 0.99};

    private final MeterRegistry registry;

    MeterEmitter(MeterRegistry registry) {
        this.registry = registry;
    }

    void count(String name, Tags tags) {
        Counter.builder(name).tags(tags).register(registry).increment();
    }

    void distribution(String name, Tags tags, double value) {
        DistributionSummary.builder(name).tags(tags)
                .publishPercentiles(PERCENTILES).register(registry).record(value);
    }

    void timing(String name, Tags tags, Duration elapsed) {
        Timer.builder(name).tags(tags).publishPercentiles(PERCENTILES).register(registry).record(elapsed);
    }
}
