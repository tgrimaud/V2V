package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.fake.FakeVectorStorePort;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.stream.IntStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class KnowledgeIngestionServiceTest {

    @Test
    void should_chunk_content_and_store_every_chunk() {
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
    void should_default_domain_to_null_overload() {
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

    @Test
    void should_store_chunks_with_ascending_zero_based_index() {
        // GIVEN a document whose paragraphs each exceed the chunk size, forcing several chunks
        FakeVectorStorePort vectorStore = new FakeVectorStorePort();
        KnowledgeIngestionService service =
                new KnowledgeIngestionService(vectorStore, new TextChunker(40, 5));

        // WHEN ingesting
        int chunks = service.ingest(
                "Aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.\n\nBbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.\n\n"
                        + "Cccccccccccccccccccccccccccccc.",
                "manual.md", "billing");

        // THEN each chunk is stored with a 0,1,2,... index; a decrement mutant on the counter would
        // store negative indices from the second chunk on.
        assertTrue(chunks >= 2, "expected the document to split into several chunks");
        List<String> expected = IntStream.range(0, chunks)
                .mapToObj(i -> "manual.md#" + i + "[billing]")
                .toList();
        assertEquals(expected, vectorStore.storedChunks);
    }
}
