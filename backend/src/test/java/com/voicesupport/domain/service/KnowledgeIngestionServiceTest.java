package com.voicesupport.domain.service;

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
        service = new KnowledgeIngestionService(vectorStorePort, 200, 30);
    }

    @Test
    void shouldSplitContentIntoChunks() {
        String content = "## Section 1\n\nParagraphe un.\n\n## Section 2\n\nParagraphe deux assez long pour tester.";

        int chunks = service.ingest(content, "test.md");

        assertTrue(chunks > 0);
        assertFalse(vectorStorePort.storedChunks.isEmpty());
    }

    @Test
    void shouldExtractSectionFromChunk() {
        String content = "## Problèmes Wi-Fi\n\nLe Wi-Fi ne fonctionne pas, vérifiez les branchements.";

        service.ingest(content, "faq.md");

        assertEquals("Problèmes Wi-Fi", vectorStorePort.storedChunks.get(0).section);
    }

    @Test
    void shouldUseSourceName() {
        service.ingest("Contenu simple.", "ma-source.md");

        assertEquals("ma-source.md", vectorStorePort.storedChunks.get(0).source);
    }

    @Test
    void shouldIngestWithDomain() {
        String content = "## Factures\n\nConsultez votre espace client pour voir vos factures.";

        int chunks = service.ingest(content, "billing-faq.md", "billing");

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

        record StoredChunk(String content, String source, String section, int chunkIndex, String domain) {}
    }
}
