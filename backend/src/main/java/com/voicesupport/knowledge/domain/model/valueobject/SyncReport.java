package com.voicesupport.knowledge.domain.model.valueobject;

// `excluded` counts documents dropped at ingestion by the audience boundary (ADR-0034,
// TASK-BE-069): internal/agent-facing content is never embedded or stored on the customer
// answer engine, so the internal partition size is observable in the sync report.
public record SyncReport(int processed, int ingested, int skipped, int deleted, int excluded) {

    public static SyncReport empty() {
        return new SyncReport(0, 0, 0, 0, 0);
    }

    public SyncReport plus(SyncReport other) {
        return new SyncReport(
                processed + other.processed,
                ingested + other.ingested,
                skipped + other.skipped,
                deleted + other.deleted,
                excluded + other.excluded);
    }
}
