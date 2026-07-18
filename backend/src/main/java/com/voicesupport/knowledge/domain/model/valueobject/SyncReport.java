package com.voicesupport.knowledge.domain.model.valueobject;

public record SyncReport(int processed, int ingested, int skipped, int deleted) {

    public static SyncReport empty() {
        return new SyncReport(0, 0, 0, 0);
    }

    public SyncReport plus(SyncReport other) {
        return new SyncReport(
                processed + other.processed,
                ingested + other.ingested,
                skipped + other.skipped,
                deleted + other.deleted);
    }
}
