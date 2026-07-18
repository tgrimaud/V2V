package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.fake.FakeKnowledgeSourceConnector;
import com.voicesupport.knowledge.fake.FakeKnowledgeSourceStatePort;
import com.voicesupport.knowledge.fake.FakeVectorStorePort;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class KnowledgeSyncServiceTest {

    private static final String TYPE = "markdown";

    private static SourceDocument doc(String id, String body) {
        return SourceDocument.create(TYPE, id, id, null, body, "billing", "fr", Instant.EPOCH);
    }

    private KnowledgeSyncService serviceWith(
            FakeKnowledgeSourceConnector connector,
            FakeKnowledgeSourceStatePort state,
            FakeVectorStorePort vectorStore) {
        return new KnowledgeSyncService(List.of(connector), state, vectorStore, new TextChunker(500, 50));
    }

    @Test
    void firstSyncIngestsAllDocuments() {
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
    void secondSyncWithUnchangedContentSkipsEverything() {
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
    void changedContentIsReingested() {
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
    void removedSourceIsDeletedViaLedgerDiff() {
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
    void syncUnknownSourceTypeThrows() {
        // GIVEN a service with only a markdown connector
        FakeKnowledgeSourceConnector connector = new FakeKnowledgeSourceConnector(TYPE, List.of());
        KnowledgeSyncService service = serviceWith(
                connector, new FakeKnowledgeSourceStatePort(), new FakeVectorStorePort());

        // WHEN syncing an unregistered source type THEN it fails fast
        assertThrows(IllegalArgumentException.class, () -> service.sync("confluence"));
    }
}
