package com.voicesupport.domain.service;

import com.voicesupport.domain.model.SourceDocument;
import com.voicesupport.domain.port.out.VectorStorePort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class KnowledgeIngestionServiceTest {

    private FakeVectorStorePort vectorStorePort;
    private KnowledgeIngestionService service;

    @BeforeEach
    void setUp() {
        vectorStorePort = new FakeVectorStorePort();
        service = new KnowledgeIngestionService(vectorStorePort, new TextChunker(200, 30));
    }

    @Test
    void ingest_splits_content_into_stored_chunks() {
        // GIVEN
        String content = "## Section 1\n\nParagraphe un.\n\n## Section 2\n\nParagraphe deux assez long pour tester.";

        // WHEN
        int chunks = service.ingest(content, "test.md");

        // THEN
        assertTrue(chunks > 0);
        assertFalse(vectorStorePort.storedChunks.isEmpty());
    }

    @Test
    void ingest_extracts_section_from_chunk() {
        // GIVEN
        String content = "## Problèmes Wi-Fi\n\nLe Wi-Fi ne fonctionne pas, vérifiez les branchements.";

        // WHEN
        service.ingest(content, "faq.md");

        // THEN
        assertEquals("Problèmes Wi-Fi", vectorStorePort.storedChunks.get(0).section);
    }

    @Test
    void ingest_uses_source_name_for_stored_chunk() {
        // GIVEN / WHEN
        service.ingest("Contenu simple.", "ma-source.md");

        // THEN
        assertEquals("ma-source.md", vectorStorePort.storedChunks.get(0).source);
    }

    @Test
    void ingest_stores_domain_when_provided() {
        // GIVEN
        String content = "## Factures\n\nConsultez votre espace client pour voir vos factures.";

        // WHEN
        int chunks = service.ingest(content, "billing-faq.md", "billing");

        // THEN
        assertTrue(chunks > 0);
        assertEquals("billing", vectorStorePort.storedChunks.get(0).domain);
    }

    static class FakeVectorStorePort implements VectorStorePort {
        final List<StoredChunk> storedChunks = new ArrayList<>();

        @Override
        public void store(String content, String source, String section, int chunkIndex) {
            store(content, source, section, chunkIndex, null);
        }

        @Override
        public void store(String content, String source, String section, int chunkIndex, String domain) {
            storedChunks.add(new StoredChunk(content, source, section, chunkIndex, domain));
        }

        @Override
        public void storeChunk(SourceDocument document, String chunkContent, String section, int chunkIndex) {
            storedChunks.add(new StoredChunk(chunkContent, document.sourceId(), section, chunkIndex, document.domain()));
        }

        @Override
        public void deleteBySource(String sourceType, String sourceId) {
            // no-op for ingestion tests
        }

        record StoredChunk(String content, String source, String section, int chunkIndex, String domain) {}
    }
}
