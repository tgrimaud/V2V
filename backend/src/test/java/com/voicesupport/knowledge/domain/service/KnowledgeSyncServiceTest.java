package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.fake.FakeKnowledgeSourceConnector;
import com.voicesupport.knowledge.fake.FakeKnowledgeSourceStatePort;
import com.voicesupport.knowledge.fake.FakeSyncObserver;
import com.voicesupport.knowledge.fake.FakeVectorStorePort;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class KnowledgeSyncServiceTest {

    private static final String TYPE = "markdown";

    private final FakeSyncObserver observer = new FakeSyncObserver();

    private static SourceDocument doc(String id, String body) {
        return SourceDocument.create(TYPE, id, id, null, body, "billing", "fr", Instant.EPOCH);
    }

    private KnowledgeSyncService serviceWith(
            FakeKnowledgeSourceConnector connector,
            FakeKnowledgeSourceStatePort state,
            FakeVectorStorePort vectorStore) {
        return new KnowledgeSyncService(
                List.of(connector), state, vectorStore, new TextChunker(500, 50), observer);
    }

    @Test
    void first_sync_ingests_all_documents() {
        // GIVEN two never-seen documents
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha."), doc("b.md", "# B\n\nBeta.")));
        FakeKnowledgeSourceStatePort state = new FakeKnowledgeSourceStatePort();
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();

        // WHEN syncing
        SyncReport report = serviceWith(connector, state, vectorStore).syncAll();

        // THEN both are ingested, none skipped or deleted
        assertEquals(2, report.processed());
        assertEquals(2, report.ingested());
        assertEquals(0, report.skipped());
        assertEquals(0, report.deleted());
    }

    @Test
    void second_sync_with_unchanged_content_skips_everything() {
        // GIVEN a source that was already synced once
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha.")));
        FakeKnowledgeSourceStatePort state = new FakeKnowledgeSourceStatePort();
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();
        KnowledgeSyncService service = serviceWith(connector, state, vectorStore);
        service.syncAll();
        int chunksAfterFirst = vectorStore.storedChunks.size();

        // WHEN syncing again with identical content
        SyncReport report = service.syncAll();

        // THEN the document is skipped and nothing new is stored (idempotent)
        assertEquals(1, report.processed());
        assertEquals(0, report.ingested());
        assertEquals(1, report.skipped());
        assertEquals(chunksAfterFirst, vectorStore.storedChunks.size());
    }

    @Test
    void changed_content_is_reingested() {
        // GIVEN a source synced once, then edited
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha.")));
        FakeKnowledgeSourceStatePort state = new FakeKnowledgeSourceStatePort();
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();
        KnowledgeSyncService service = serviceWith(connector, state, vectorStore);
        service.syncAll();

        // WHEN content changes and we sync again
        connector.setDocuments(List.of(doc("a.md", "# A\n\nAlpha REVISED.")));
        SyncReport report = service.syncAll();

        // THEN the document is re-ingested (its old chunks are deleted first)
        assertEquals(1, report.ingested());
        assertEquals(0, report.skipped());
        assertTrue(vectorStore.deletedSources.contains(TYPE + "/a.md"));
    }

    @Test
    void removed_source_is_deleted_via_ledger_diff() {
        // GIVEN two synced sources
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha."), doc("b.md", "# B\n\nBeta.")));
        FakeKnowledgeSourceStatePort state = new FakeKnowledgeSourceStatePort();
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();
        KnowledgeSyncService service = serviceWith(connector, state, vectorStore);
        service.syncAll();

        // WHEN one source disappears from the connector
        connector.setDocuments(List.of(doc("a.md", "# A\n\nAlpha.")));
        SyncReport report = service.syncAll();

        // THEN the stale source is deleted from the store and the ledger
        assertEquals(1, report.deleted());
        assertTrue(vectorStore.deletedSources.contains(TYPE + "/b.md"));
        assertEquals(List.of("a.md"), state.listSourceIds(TYPE));
    }

    @Test
    void sync_single_source_type_returns_report_for_the_matching_connector() {
        // GIVEN a service with a markdown connector holding two never-seen documents
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha."), doc("b.md", "# B\n\nBeta.")));
        KnowledgeSyncService service = serviceWith(
                connector, new FakeKnowledgeSourceStatePort(), new FakeVectorStorePort());

        // WHEN syncing that single source type by name
        SyncReport report = service.sync(TYPE);

        // THEN the matching connector is selected and its report is returned (not null, not thrown);
        // pins the `sourceType.equals(...)` predicate and the non-null return of the single-source path
        assertEquals(2, report.processed());
        assertEquals(2, report.ingested());
    }

    @Test
    void remove_stale_deletes_the_stale_source_from_the_vector_store() {
        // GIVEN two synced sources
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha."), doc("b.md", "# B\n\nBeta.")));
        FakeKnowledgeSourceStatePort state = new FakeKnowledgeSourceStatePort();
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();
        KnowledgeSyncService service = serviceWith(connector, state, vectorStore);
        service.syncAll();
        // Isolate the removeStale deletion from the delete-before-store done during first ingestion
        vectorStore.deletedSources.clear();

        // WHEN one unchanged source remains and the other disappears (a.md is skipped, not re-ingested)
        connector.setDocuments(List.of(doc("a.md", "# A\n\nAlpha.")));
        service.syncAll();

        // THEN the stale source is deleted from the vector store via removeStale specifically; a mutant
        // that removes that deleteBySource call leaves the store untouched here.
        assertEquals(List.of(TYPE + "/b.md"), vectorStore.deletedSources);
    }

    @Test
    void sync_unknown_source_type_throws() {
        // GIVEN a service with only a markdown connector
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(TYPE, List.of());
        KnowledgeSyncService service = serviceWith(
                connector, new FakeKnowledgeSourceStatePort(), new FakeVectorStorePort());

        // WHEN syncing an unregistered source type THEN it fails fast
        assertThrows(IllegalArgumentException.class, () -> service.sync("confluence"));
    }

    @Test
    void each_document_is_stored_in_one_batched_call() {
        // GIVEN two documents to ingest
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha."), doc("b.md", "# B\n\nBeta.")));
        FakeKnowledgeSourceStatePort state = new FakeKnowledgeSourceStatePort();
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();

        // WHEN syncing
        serviceWith(connector, state, vectorStore).syncAll();

        // THEN the vector store is written once per document (batched), not once per chunk
        assertEquals(2, vectorStore.storeChunksCalls);
    }

    @Test
    void observer_receives_per_batch_timing_and_completion_totals() {
        // GIVEN two documents to ingest
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha."), doc("b.md", "# B\n\nBeta.")));
        FakeKnowledgeSourceStatePort state = new FakeKnowledgeSourceStatePort();
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();

        // WHEN syncing
        serviceWith(connector, state, vectorStore).syncAll();

        // THEN one batch event per ingested document and a single completion with matching totals
        assertEquals(2, observer.batches.size());
        assertEquals(1, observer.completions.size());
        FakeSyncObserver.Completion completion = observer.completions.get(0);
        assertEquals(TYPE, completion.sourceType());
        assertEquals(2, completion.report().ingested());
        int chunksFromBatches = observer.batches.stream().mapToInt(FakeSyncObserver.Batch::chunkCount).sum();
        assertEquals(chunksFromBatches, completion.totalChunks());
        assertEquals(vectorStore.storedChunks.size(), completion.totalChunks());
    }

    @Test
    void failed_batch_aborts_sync_but_is_observable_and_resumable() {
        // GIVEN two documents where the second fails to store
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha."), doc("b.md", "# B\n\nBeta.")));
        FakeKnowledgeSourceStatePort state = new FakeKnowledgeSourceStatePort();
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();
        vectorStore.failOnSourceId = "b.md";
        KnowledgeSyncService service = serviceWith(connector, state, vectorStore);

        // WHEN syncing THEN it fails fast (the exception propagates to the caller)
        assertThrows(IllegalStateException.class, service::syncAll);

        // AND the failure is observable with the progress achieved before the abort (no completion)
        assertEquals(1, observer.failures.size());
        FakeSyncObserver.Failure failure = observer.failures.get(0);
        assertEquals(TYPE, failure.sourceType());
        assertEquals(1, failure.ingestedSoFar());
        assertEquals("IllegalStateException", failure.errorCode());
        assertTrue(observer.completions.isEmpty());

        // AND the first document is committed (ledger) so the next idempotent sync resumes it
        assertEquals(List.of("a.md"), state.listSourceIds(TYPE));
    }

    @Test
    void unchanged_documents_emit_no_batch_but_still_complete() {
        // GIVEN a source already synced once
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(
                TYPE, List.of(doc("a.md", "# A\n\nAlpha.")));
        FakeKnowledgeSourceStatePort state = new FakeKnowledgeSourceStatePort();
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();
        KnowledgeSyncService service = serviceWith(connector, state, vectorStore);
        service.syncAll();
        observer.batches.clear();
        observer.completions.clear();

        // WHEN syncing again with identical content
        service.syncAll();

        // THEN no batch is stored (idempotent) but the completion still fires with zero chunks
        assertTrue(observer.batches.isEmpty());
        assertEquals(1, observer.completions.size());
        assertEquals(0, observer.completions.get(0).totalChunks());
    }
}
