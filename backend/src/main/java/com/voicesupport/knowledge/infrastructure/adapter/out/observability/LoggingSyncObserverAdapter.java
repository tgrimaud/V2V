package com.voicesupport.knowledge.infrastructure.adapter.out.observability;

import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.port.out.SyncObserverPort;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

// Turns KB-sync domain events (TASK-BE-014) into Micrometer metrics + [KB-SYNC] structured logs.
// Metrics (tagged by source_type, bounded cardinality): voice_support.kb_sync_batch (per-document
// embedding+insert latency, p50/p95/p99), voice_support.kb_sync_chunks (chunks per document) and
// voice_support.kb_sync (full-sync wall clock). Per-batch detail is DEBUG (avoids 40k INFO lines);
// an INFO progress line lands every N batches; the completion line carries throughput (chunks/s).
@Component
public class LoggingSyncObserverAdapter implements SyncObserverPort {

    private static final Logger log = LoggerFactory.getLogger(LoggingSyncObserverAdapter.class);
    private static final String BATCH_TIMER = "voice_support.kb_sync_batch";
    private static final String CHUNKS_SUMMARY = "voice_support.kb_sync_chunks";
    private static final String SYNC_TIMER = "voice_support.kb_sync";
    private static final String SYNC_FAILURES = "voice_support.kb_sync_failures";

    private final MeterRegistry registry;
    private final int progressEvery;
    private final Map<String, AtomicInteger> batchCounters = new ConcurrentHashMap<>();

    public LoggingSyncObserverAdapter(
            MeterRegistry registry,
            @Value("${voice-support.knowledge.sync-progress-every:500}") int progressEvery) {
        this.registry = registry;
        this.progressEvery = progressEvery > 0 ? progressEvery : 500;
    }

    @Override
    public void batchStored(String sourceType, String sourceId, int chunkCount, long elapsedMs) {
        Timer.builder(BATCH_TIMER).tag("source_type", sourceType)
                .publishPercentiles(0.5, 0.95, 0.99).register(registry)
                .record(Duration.ofMillis(elapsedMs));
        DistributionSummary.builder(CHUNKS_SUMMARY).tag("source_type", sourceType)
                .register(registry).record(chunkCount);
        log.debug("[KB-SYNC] op=batch source_type={} source_id={} chunks={} duration_ms={}",
                sourceType, sourceId, chunkCount, elapsedMs);
        int done = batchCounters.computeIfAbsent(sourceType, k -> new AtomicInteger()).incrementAndGet();
        if (done % progressEvery == 0) {
            log.info("[KB-SYNC] op=progress source_type={} batches_ingested={}", sourceType, done);
        }
    }

    @Override
    public void syncCompleted(String sourceType, SyncReport report, int totalChunks, long durationMs) {
        batchCounters.remove(sourceType);
        Timer.builder(SYNC_TIMER).tag("source_type", sourceType).register(registry)
                .record(Duration.ofMillis(durationMs));
        double chunksPerSec = durationMs > 0 ? totalChunks * 1000.0 / durationMs : 0.0;
        log.info("[KB-SYNC] op=sync-detail source_type={} processed={} ingested={} skipped={} "
                        + "deleted={} total_chunks={} duration_ms={} chunks_per_sec={}",
                sourceType, report.processed(), report.ingested(), report.skipped(),
                report.deleted(), totalChunks, durationMs,
                String.format(Locale.ROOT, "%.1f", chunksPerSec));
    }

    @Override
    public void syncFailed(String sourceType, int ingestedSoFar, int totalChunksSoFar, long durationMs, String errorCode) {
        batchCounters.remove(sourceType);
        // error_code is a bounded exception class name (e.g. RuntimeException); safe as a metric tag.
        registry.counter(SYNC_FAILURES, "source_type", sourceType, "error_code", errorCode).increment();
        log.warn("[KB-SYNC] op=sync-failed source_type={} ingested_so_far={} total_chunks_so_far={} "
                        + "duration_ms={} error_code={} (fail-fast; committed documents resume on next sync)",
                sourceType, ingestedSoFar, totalChunksSoFar, durationMs, errorCode);
    }
}
