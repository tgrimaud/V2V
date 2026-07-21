package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.port.out.SyncObserverPort;

import java.util.ArrayList;
import java.util.List;

public class FakeSyncObserver implements SyncObserverPort {

    public record Batch(String sourceType, String sourceId, int chunkCount, long elapsedMs) {
    }

    public record Completion(String sourceType, SyncReport report, int totalChunks, long durationMs) {
    }

    public final List<Batch> batches = new ArrayList<>();
    public final List<Completion> completions = new ArrayList<>();

    @Override
    public void batchStored(String sourceType, String sourceId, int chunkCount, long elapsedMs) {
        batches.add(new Batch(sourceType, sourceId, chunkCount, elapsedMs));
    }

    @Override
    public void syncCompleted(String sourceType, SyncReport report, int totalChunks, long durationMs) {
        completions.add(new Completion(sourceType, report, totalChunks, durationMs));
    }
}
