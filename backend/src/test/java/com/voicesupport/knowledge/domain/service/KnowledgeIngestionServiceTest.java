package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.fake.FakeVectorStorePort;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class KnowledgeIngestionServiceTest {

    @Test
    void shouldChunkContentAndStoreEveryChunk() {
        // GIVEN an ingestion service over a fake vector store
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();
        KnowledgeIngestionService service =
                new KnowledgeIngestionService(vectorStore, new TextChunker(40, 5));

        // WHEN ingesting a multi-paragraph document
        int chunks = service.ingest(
                "Para one is here.\n\nPara two is here.\n\nPara three is here.",
                "manual.md", "billing");

        // THEN every produced chunk is stored and the count is returned
        assertEquals(chunks, vectorStore.storedChunks.size());
    }

    @Test
    void shouldDefaultDomainToNullOverload() {
        // GIVEN an ingestion service
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();
        KnowledgeIngestionService service =
                new KnowledgeIngestionService(vectorStore, new TextChunker(500, 50));

        // WHEN ingesting without an explicit domain
        int chunks = service.ingest("# Title\n\nBody.", "manual.md");

        // THEN a single chunk is stored
        assertEquals(1, chunks);
        assertEquals(1, vectorStore.storedChunks.size());
    }
}
