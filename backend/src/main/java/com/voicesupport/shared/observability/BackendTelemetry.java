package com.voicesupport.shared.observability;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
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
    private static final String ANSWER_CHARS = "voice_support.answer_chars";
    private static final String ANSWER_LANGUAGE = "voice_support.answer_language";
    private static final String GUARDRAIL_BLOCK = "voice_support.guardrail_block";
    private static final String BILLING_CLARIFY = "voice_support.billing_clarify";
    private static final String CHANNEL_DELIVERY = "voice_support.channel_delivery";
    private static final String ESCALATION_HANDOFF = "voice_support.escalation_handoff";
    private static final String OUTCOME_SUCCESS = "success";
    private static final String OUTCOME_ERROR = "error";
    // Optional non-PII refinement of an outcome (e.g. why a billing turn escalated). Kept uniform
    // across all slices so the voice_support.slice timer always carries the same tag keys.
    private static final String REASON_NONE = "n/a";
    private static final String CHANNEL_NONE = "n/a";
    private static final String CHANNEL_OTHER = "other";
    // `web_voice` is the web Voice2Voice runtime channel (TASK-BE-008) and `genesys` is the Genesys
    // Audio Connector channel (TASK-BE-037) — both kept first-class so the real spoken paths are
    // reportable per channel instead of collapsing into `other`. Env-overridable via
    // voice-support.observability.allowed-channels.
    private static final String DEFAULT_ALLOWED_CHANNELS = "web,web_voice,phone,whatsapp,genesys,api";

    private final MeterEmitter meters;
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
        this.meters = new MeterEmitter(registry);
        this.allowedChannels = Arrays.stream(allowedChannelsCsv.split(","))
                .map(String::trim).map(s -> s.toLowerCase(java.util.Locale.ROOT))
                .filter(s -> !s.isBlank()).collect(Collectors.toUnmodifiableSet());
    }

    // One-shot latency recording for streamed slices (TASK-BE-007): first-token and stream-total
    // timings are measured by the caller (there is no Supplier to wrap around a push stream), so
    // they are recorded on the same timer/log as time(...) with an explicit outcome.
    public void recordLatency(String slice, String provider, String outcome, Duration elapsed) {
        record(slice, provider, outcome == null ? OUTCOME_SUCCESS : outcome, REASON_NONE, elapsed.toNanos());
    }

    // Same as recordLatency but carries an optional non-PII outcome refinement (TASK-BE-048): the
    // billing seam uses it to distinguish why a not_enough_data turn escalated (insufficient history
    // vs unfetchable evidence vs reconciliation gap) without changing the stable `outcome` tag.
    public void recordLatency(String slice, String provider, String outcome, String reason, Duration elapsed) {
        record(slice, provider, outcome == null ? OUTCOME_SUCCESS : outcome, reason, elapsed.toNanos());
    }

    // Prompt-size observability (TASK-BE-011): records the char breakdown of the LLM system
    // message (fixed instructions + RAG context + history) and the retrieved chunk count as a
    // DistributionSummary (voice_support.prompt_chars) plus a [PROMPT] log, so a slow
    // llm_first_token can be correlated with prompt size when tuning top-K / prompt length.
    // Records lengths and counts only — never prompt content — and carries the correlation id.
    public void recordPromptSize(String provider, int systemChars, int contextChars, int historyChars, int chunkCount) {
        String safeProvider = provider == null || provider.isBlank() ? "n/a" : provider;
        meters.distribution(PROMPT_CHARS, Tags.of("provider", safeProvider), systemChars);
        log.info("[PROMPT] provider={} system_chars={} context_chars={} history_chars={} chunk_count={} "
                        + "correlation_id={}",
                safeProvider, systemChars, contextChars, historyChars, chunkCount, CorrelationId.current());
    }

    // Answer-length observability (TASK-BE-018): records the spoken answer size in characters as a
    // DistributionSummary (voice_support.answer_chars) plus an [ANSWER] log, so the concision budget's
    // effect on TTS synthesis time is measurable next to the llm_wording latency. Records the length
    // only — never the answer text — and carries the correlation id.
    public void recordAnswerLength(String provider, int answerChars) {
        String safeProvider = provider == null || provider.isBlank() ? "n/a" : provider;
        meters.distribution(ANSWER_CHARS, Tags.of("provider", safeProvider), answerChars);
        log.info("[ANSWER] provider={} answer_chars={} correlation_id={}",
                safeProvider, answerChars, CorrelationId.current());
    }

    // Answer-language observability (TASK-BE-015): records the language the assistant answered in
    // for the turn as a counter (voice_support.answer_language) tagged by provider + language, plus
    // a [LANGUAGE] structured log with the correlation id. Records the language code only — never
    // transcript or answer text — so QA can verify the customer was answered in the right language.
    public void recordAnswerLanguage(String provider, String language) {
        String safeProvider = provider == null || provider.isBlank() ? "n/a" : provider;
        String safeLanguage = language == null || language.isBlank() ? "n/a" : language;
        meters.count(ANSWER_LANGUAGE, Tags.of("provider", safeProvider, "language", safeLanguage));
        log.info("[LANGUAGE] provider={} language={} correlation_id={}",
                safeProvider, safeLanguage, CorrelationId.current());
    }

    // Guardrail-block observability (ADR-0034): counts turns short-circuited by a blocked guardrail
    // decision (voice_support.guardrail_block, tagged verdict + channel) plus a [GUARDRAIL] log, so
    // clarify vs low_confidence vs off_topic rates are measurable per channel (BUG-005). Records the
    // verdict only — never transcript or answer text — and carries the correlation id.
    public void recordGuardrailBlock(String verdict) {
        recordGuardrailBlock(verdict, null);
    }

    // BUG-025: an optional low-cardinality reason sub-tag lets QA/Ops separate otherwise-identical
    // verdicts (e.g. a problem-opener CLARIFY from a vague/mid-confidence CLARIFY). Reason only —
    // never transcript or answer text — so no PII leaks into metrics/logs.
    public void recordGuardrailBlock(String verdict, String reason) {
        String safeVerdict = verdict == null || verdict.isBlank()
                ? "n/a" : verdict.toLowerCase(java.util.Locale.ROOT);
        String safeReason = reason == null || reason.isBlank()
                ? "n/a" : reason.toLowerCase(java.util.Locale.ROOT);
        String channel = normalizeChannel(CorrelationId.currentChannel());
        meters.count(GUARDRAIL_BLOCK, Tags.of("verdict", safeVerdict, "reason", safeReason, "channel", channel));
        log.info("[GUARDRAIL] verdict={} reason={} channel={} correlation_id={}",
                safeVerdict, safeReason, channel, CorrelationId.current());
    }

    // US-043 / TASK-BE-071: bounded billing clarify observability. Counts clarify-dialogue events
    // (voice_support.billing_clarify, tagged event asked|cap_escalated + language + channel) plus a
    // [BILLING-CLARIFY] structured log carrying the current clarify count and the correlation id, so
    // QA/Ops can measure how often the bot clarifies, the per-conversation depth, and the cap-hit rate
    // (US-043 analytics). Records technical dimensions only — never the transcript or the question text.
    public void recordBillingClarify(String event, String language, int count) {
        String channel = normalizeChannel(CorrelationId.currentChannel());
        String safeEvent = event == null || event.isBlank() ? "n/a" : event;
        String safeLanguage = language == null || language.isBlank() ? "n/a" : language;
        meters.count(BILLING_CLARIFY, Tags.of("event", safeEvent, "language", safeLanguage, "channel", channel));
        log.info("[BILLING-CLARIFY] event={} language={} count={} channel={} correlation_id={}",
                safeEvent, safeLanguage, count, channel, CorrelationId.current());
    }

    // Normalized channel envelope observability (TASK-BE-037, ADR-0009): counts inbound channel
    // deliveries (voice_support.channel_delivery) tagged channel + reply_mode + duplicate, plus a
    // [CHANNEL] structured log with the correlation id, so per-channel volume and the duplicate
    // (idempotent re-delivery) rate are measurable. Records technical dimensions only — never the
    // transcript, session id or escalation context.
    public void recordChannelDelivery(String replyMode, boolean duplicate) {
        String channel = normalizeChannel(CorrelationId.currentChannel());
        String safeReplyMode = replyMode == null || replyMode.isBlank() ? "n/a" : replyMode;
        meters.count(CHANNEL_DELIVERY,
                Tags.of("channel", channel, "reply_mode", safeReplyMode, "duplicate", Boolean.toString(duplicate)));
        log.info("[CHANNEL] channel={} reply_mode={} duplicate={} correlation_id={}",
                channel, safeReplyMode, duplicate, CorrelationId.current());
    }

    // Escalation hand-off observability (TASK-BE-036 / DEC-013): counts the by-reference hand-off
    // lifecycle (voice_support.escalation_handoff, tagged outcome created|fetched|not_found +
    // reason_code + channel) plus a [HANDOFF] structured log with the correlation id and the opaque
    // handoff_id. The handoff_id (a UUID) and reason_code are non-PII; the summary, last user message
    // and customer reference are never recorded here — they stay behind the audited fetch (ADR-0040).
    public void recordEscalationHandoff(String outcome, String reasonCode, String handoffId) {
        String channel = normalizeChannel(CorrelationId.currentChannel());
        String safeOutcome = outcome == null || outcome.isBlank() ? "n/a" : outcome;
        String safeReason = reasonCode == null || reasonCode.isBlank() ? "n/a" : reasonCode;
        meters.count(ESCALATION_HANDOFF,
                Tags.of("outcome", safeOutcome, "reason_code", safeReason, "channel", channel));
        log.info("[HANDOFF] outcome={} reason_code={} channel={} handoff_id={} correlation_id={}",
                safeOutcome, safeReason, channel, CorrelationId.sanitize(handoffId), CorrelationId.current());
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
            record(slice, provider, outcome, REASON_NONE, System.nanoTime() - start);
        }
    }

    private void record(String slice, String provider, String outcome, String reason, long elapsedNanos) {
        String channel = normalizeChannel(CorrelationId.currentChannel());
        String safeProvider = provider == null || provider.isBlank() ? "n/a" : provider;
        String safeReason = reason == null || reason.isBlank() ? REASON_NONE : reason;
        meters.timing(TIMER,
                Tags.of("slice", slice, "channel", channel, "provider", safeProvider,
                        "outcome", outcome, "reason", safeReason),
                Duration.ofNanos(elapsedNanos));
        log.info("[TELEMETRY] slice={} channel={} provider={} outcome={} reason={} correlation_id={} duration_ms={}",
                slice, channel, safeProvider, outcome, safeReason, CorrelationId.current(), elapsedNanos / 1_000_000);
    }

    private String normalizeChannel(String raw) {
        if (raw == null || raw.isBlank() || CHANNEL_NONE.equalsIgnoreCase(raw.trim())) {
            return CHANNEL_NONE;
        }
        String candidate = raw.trim().toLowerCase(java.util.Locale.ROOT);
        return allowedChannels.contains(candidate) ? candidate : CHANNEL_OTHER;
    }
}
