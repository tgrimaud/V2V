package com.voicesupport.knowledge.infrastructure.adapter.out.observability;

import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class LoggingSyncObserverAdapterTest {

    private static final String TYPE = "csv-article";

    @Test
    void batchStoredRegistersBatchTimerAndChunkSummary() {
        // GIVEN an observer backed by a real (in-memory) meter registry
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        LoggingSyncObserverAdapter observer = new LoggingSyncObserverAdapter(registry, 500);

        // WHEN two document batches are stored
        observer.batchStored(TYPE, "196", 10, 120);
        observer.batchStored(TYPE, "197", 4, 40);

        // THEN the per-batch timer counts both and the chunk summary totals their chunks
        assertEquals(2, registry.get("voice_support.kb_sync_batch").tag("source_type", TYPE).timer().count());
        assertEquals(14.0,
                registry.get("voice_support.kb_sync_chunks").tag("source_type", TYPE).summary().totalAmount());
    }

    @Test
    void syncCompletedRegistersFullSyncTimer() {
        // GIVEN an observer backed by a real meter registry
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        LoggingSyncObserverAdapter observer = new LoggingSyncObserverAdapter(registry, 500);

        // WHEN a connector sync completes
        observer.syncCompleted(TYPE, new SyncReport(150, 150, 0, 0), 1901, 44504);

        // THEN the full-sync timer is registered for that source type
        assertNotNull(registry.get("voice_support.kb_sync").tag("source_type", TYPE).timer());
        assertEquals(1, registry.get("voice_support.kb_sync").tag("source_type", TYPE).timer().count());
    }

    @Test
    void syncFailedIncrementsFailureCounterTaggedByErrorCode() {
        // GIVEN an observer backed by a real meter registry
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        LoggingSyncObserverAdapter observer = new LoggingSyncObserverAdapter(registry, 500);

        // WHEN a sync aborts mid-run
        observer.syncFailed(TYPE, 42, 900, 30000, "IllegalStateException");

        // THEN a failure counter is incremented, tagged by source_type and (bounded) error_code
        assertEquals(1.0, registry.get("voice_support.kb_sync_failures")
                .tag("source_type", TYPE).tag("error_code", "IllegalStateException").counter().count());
    }
}
