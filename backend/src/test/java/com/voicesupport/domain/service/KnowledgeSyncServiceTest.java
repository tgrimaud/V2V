package com.voicesupport.domain.service;

import com.voicesupport.domain.model.SourceDocument;
import com.voicesupport.domain.model.SyncReport;
import com.voicesupport.domain.port.out.KnowledgeSourceConnector;
import com.voicesupport.domain.port.out.KnowledgeSourceStatePort;
import com.voicesupport.domain.port.out.VectorStorePort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class KnowledgeSyncServiceTest {

    private FakeConnector connector;
    private FakeStatePort statePort;
    private RecordingVectorStorePort vectorStorePort;
    private KnowledgeSyncService service;

    @BeforeEach
    void setUp() {
        connector = new FakeConnector("markdown");
        statePort = new FakeStatePort();
        vectorStorePort = new RecordingVectorStorePort();
        service = new KnowledgeSyncService(
                List.of(connector), statePort, vectorStorePort, new TextChunker(500, 50));
    }

    @Test
    void shouldIngestNewDocument() {
        connector.add(doc("faq.md", "## Titre\n\nContenu initial."));

        SyncReport report = service.syncAll();

        assertEquals(1, report.ingested());
        assertEquals(0, report.skipped());
        assertFalse(vectorStorePort.storedChunks.isEmpty());
        assertTrue(statePort.findHash("markdown", "faq.md").isPresent());
    }

    @Test
    void shouldSkipUnchangedDocument() {
        SourceDocument document = doc("faq.md", "## Titre\n\nContenu stable.");
        statePort.upsertState("markdown", "faq.md", document.contentHash(), document.updatedAt(), 1);
        connector.add(document);

        SyncReport report = service.syncAll();

        assertEquals(0, report.ingested());
        assertEquals(1, report.skipped());
        assertTrue(vectorStorePort.storedChunks.isEmpty());
        assertTrue(vectorStorePort.deletedSources.isEmpty());
    }

    @Test
    void shouldReingestChangedDocument() {
        statePort.upsertState("markdown", "faq.md", "ancien-hash", Instant.now(), 1);
        connector.add(doc("faq.md", "## Titre\n\nNouveau contenu modifie."));

        SyncReport report = service.syncAll();

        assertEquals(1, report.ingested());
        assertEquals(0, report.skipped());
        assertTrue(vectorStorePort.deletedSources.contains("markdown::faq.md"));
        assertFalse(vectorStorePort.storedChunks.isEmpty());
    }

    @Test
    void shouldDeleteStaleDocumentNoLongerInSource() {
        statePort.upsertState("markdown", "obsolete.md", "hash", Instant.now(), 2);
        connector.add(doc("faq.md", "## Titre\n\nContenu present."));

        SyncReport report = service.syncAll();

        assertEquals(1, report.deleted());
        assertTrue(vectorStorePort.deletedSources.contains("markdown::obsolete.md"));
        assertTrue(statePort.findHash("markdown", "obsolete.md").isEmpty());
    }

    @Test
    void shouldThrowWhenSyncingUnknownSourceType() {
        assertThrows(IllegalArgumentException.class, () -> service.sync("pdf"));
    }

    private SourceDocument doc(String sourceId, String content) {
        return SourceDocument.create("markdown", sourceId, "Titre", null, content, "support", "fr", Instant.now());
    }

    static class FakeConnector implements KnowledgeSourceConnector {
        private final String sourceType;
        private final List<SourceDocument> documents = new ArrayList<>();

        FakeConnector(String sourceType) {
            this.sourceType = sourceType;
        }

        void add(SourceDocument document) {
            documents.add(document);
        }

        @Override
        public String sourceType() {
            return sourceType;
        }

        @Override
        public List<SourceDocument> fetchAll() {
            return documents;
        }
    }

    static class FakeStatePort implements KnowledgeSourceStatePort {
        private final Map<String, String> hashes = new HashMap<>();

        private String key(String type, String id) {
            return type + "::" + id;
        }

        @Override
        public Optional<String> findHash(String sourceType, String sourceId) {
            return Optional.ofNullable(hashes.get(key(sourceType, sourceId)));
        }

        @Override
        public void upsertState(String sourceType, String sourceId, String contentHash, Instant updatedAt, int chunkCount) {
            hashes.put(key(sourceType, sourceId), contentHash);
        }

        @Override
        public List<String> listSourceIds(String sourceType) {
            return hashes.keySet().stream()
                    .filter(k -> k.startsWith(sourceType + "::"))
                    .map(k -> k.substring((sourceType + "::").length()))
                    .toList();
        }

        @Override
        public void deleteState(String sourceType, String sourceId) {
            hashes.remove(key(sourceType, sourceId));
        }
    }

    static class RecordingVectorStorePort implements VectorStorePort {
        final List<String> storedChunks = new ArrayList<>();
        final List<String> deletedSources = new ArrayList<>();

        @Override
        public void store(String content, String source, String section, int chunkIndex) {
        }

        @Override
        public void store(String content, String source, String section, int chunkIndex, String domain) {
        }

        @Override
        public void storeChunk(SourceDocument document, String chunkContent, String section, int chunkIndex) {
            storedChunks.add(document.sourceId() + "#" + chunkIndex);
        }

        @Override
        public void deleteBySource(String sourceType, String sourceId) {
            deletedSources.add(sourceType + "::" + sourceId);
        }
    }
}
