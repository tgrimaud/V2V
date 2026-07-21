package com.voicesupport.knowledge.domain.port.out;

import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;

// Observability hook for the KB sync (TASK-BE-014). The domain reports progress and timing;
// the infra adapter turns it into Micrometer metrics + [KB-SYNC] structured logs. Kept as a
// domain out-port so the sync service stays pure and testable with a fake (no Micrometer/SLF4J).
public interface SyncObserverPort {

    // One document (a "batch" of chunks) has been embedded + stored. elapsedMs covers only the
    // vector-store write, so per-batch embedding/insert latency is measurable as a distribution.
    void batchStored(String sourceType, String sourceId, int chunkCount, long elapsedMs);

    // A connector sync finished: full counts, total chunks written and wall-clock duration so
    // throughput (chunks/s) can be reported for the bulk-ingest latency evidence.
    void syncCompleted(String sourceType, SyncReport report, int totalChunks, long durationMs);
}
