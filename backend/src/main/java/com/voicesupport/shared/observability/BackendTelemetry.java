package com.voicesupport.shared.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
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
    private static final String PROMPT_CHARS = "voice_support.prompt_chars";
    private static final String ANSWER_LANGUAGE = "voice_support.answer_language";
    private static final String OUTCOME_SUCCESS = "success";
    private static final String OUTCOME_ERROR = "error";
    private static final String CHANNEL_NONE = "n/a";
    private static final String CHANNEL_OTHER = "other";
    // `web_voice` is the web Voice2Voice runtime channel (TASK-BE-008) — kept first-class so the
    // real spoken path is reportable per channel instead of collapsing into `other`.
    private static final String DEFAULT_ALLOWED_CHANNELS = "web,web_voice,phone,whatsapp,api";

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

    // One-shot latency recording for streamed slices (TASK-BE-007): first-token and stream-total
    // timings are measured by the caller (there is no Supplier to wrap around a push stream), so
    // they are recorded on the same timer/log as time(...) with an explicit outcome.
    public void recordLatency(String slice, String provider, String outcome, Duration elapsed) {
        record(slice, provider, outcome == null ? OUTCOME_SUCCESS : outcome, elapsed.toNanos());
    }

    // Prompt-size observability (TASK-BE-011): records the char breakdown of the LLM system
    // message (fixed instructions + RAG context + history) and the retrieved chunk count as a
    // DistributionSummary (voice_support.prompt_chars) plus a [PROMPT] log, so a slow
    // llm_first_token can be correlated with prompt size when tuning top-K / prompt length.
    // Records lengths and counts only — never prompt content — and carries the correlation id.
    public void recordPromptSize(String provider, int systemChars, int contextChars, int historyChars, int chunkCount) {
        String safeProvider = provider == null || provider.isBlank() ? "n/a" : provider;
        DistributionSummary.builder(PROMPT_CHARS)
                .tag("provider", safeProvider)
                .publishPercentiles(0.5, 0.95, 0.99)
                .register(registry)
                .record(systemChars);
        log.info("[PROMPT] provider={} system_chars={} context_chars={} history_chars={} chunk_count={} "
                        + "correlation_id={}",
                safeProvider, systemChars, contextChars, historyChars, chunkCount, CorrelationId.current());
    }

    // Answer-language observability (TASK-BE-015): records the language the assistant answered in
    // for the turn as a counter (voice_support.answer_language) tagged by provider + language, plus
    // a [LANGUAGE] structured log with the correlation id. Records the language code only — never
    // transcript or answer text — so QA can verify the customer was answered in the right language.
    public void recordAnswerLanguage(String provider, String language) {
        String safeProvider = provider == null || provider.isBlank() ? "n/a" : provider;
        String safeLanguage = language == null || language.isBlank() ? "n/a" : language;
        Counter.builder(ANSWER_LANGUAGE)
                .tag("provider", safeProvider)
                .tag("language", safeLanguage)
                .register(registry)
                .increment();
        log.info("[LANGUAGE] provider={} language={} correlation_id={}",
                safeProvider, safeLanguage, CorrelationId.current());
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
