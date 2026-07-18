package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.fake.FakeVectorSearchPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("KnowledgeRetrievalService (query embed + domain-filtered top-k)")
class KnowledgeRetrievalServiceTest {

    private FakeVectorSearchPort vectorSearch;
    private KnowledgeRetrievalService service;

    @BeforeEach
    void setUp() {
        vectorSearch = new FakeVectorSearchPort();
        service = new KnowledgeRetrievalService(vectorSearch);
    }

    @Test
    @DisplayName("delegates query, domain and top-k to the vector search port")
    void delegatesToVectorSearch() {
        // GIVEN the store returns one chunk
        vectorSearch.setResults(List.of(new KnowledgeChunk("proration", "billing-faq#1", "billing", 0.8)));

        // WHEN retrieving with an explicit domain and top-k
        List<KnowledgeChunk> chunks = service.retrieve("why higher", "billing", 3);

        // THEN the port is called with the same arguments
        assertEquals(1, chunks.size());
        assertEquals("why higher", vectorSearch.lastQuery);
        assertEquals("billing", vectorSearch.lastDomain);
        assertEquals(3, vectorSearch.lastTopK);
    }

    @Test
    @DisplayName("applies a default top-k when a non-positive value is requested")
    void appliesDefaultTopK() {
        // WHEN retrieving with topK = 0
        service.retrieve("question", "support", 0);

        // THEN the default top-k is used
        assertEquals(4, vectorSearch.lastTopK);
    }

    @Test
    @DisplayName("normalizes a blank domain to no restriction")
    void normalizesBlankDomain() {
        // WHEN retrieving with a blank domain
        service.retrieve("question", "  ", 2);

        // THEN the port receives a null domain (no restriction)
        assertEquals(null, vectorSearch.lastDomain);
    }

    @Test
    @DisplayName("short-circuits a blank query without hitting the store")
    void shortCircuitsBlankQuery() {
        // WHEN retrieving with a blank query
        List<KnowledgeChunk> chunks = service.retrieve("   ", "billing", 3);

        // THEN no search happens and the result is empty
        assertTrue(chunks.isEmpty());
        assertEquals(0, vectorSearch.callCount);
    }
}
