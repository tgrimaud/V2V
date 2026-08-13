package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.fake.FakeRetrievalObserverPort;
import com.voicesupport.knowledge.fake.FakeVectorSearchPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
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

    @Test
    @DisplayName("with MMR enabled, over-fetches top-k * multiplier then re-selects a diverse top-k")
    void mmrOverFetchesThenReselects() {
        // GIVEN MMR is wired with a x3 over-fetch, and the store returns near-duplicate headers plus
        // a distinct answer chunk — plain top-2 by score would evict the answer (BUG-003)
        FakeRetrievalObserverPort observer = new FakeRetrievalObserverPort();
        KnowledgeRetrievalService mmrService = new KnowledgeRetrievalService(
                vectorSearch, new MmrReranker(0.7), observer, 3);
        vectorSearch.setResults(List.of(
                new KnowledgeChunk("wifi help wifi help wifi help", "h1", "support", 0.82),
                new KnowledgeChunk("wifi help wifi help wifi help now", "h2", "support", 0.81),
                new KnowledgeChunk("restart the router to fix a slow connection", "ans", "support", 0.80)));

        // WHEN retrieving the top-2
        List<KnowledgeChunk> chunks = mmrService.retrieve("why is my wifi slow", "support", 2);

        // THEN the store was over-fetched (2 * 3 = 6) and MMR kept the answer chunk over a redundant header
        assertEquals(6, vectorSearch.lastTopK);
        assertEquals(2, chunks.size());
        assertTrue(chunks.stream().anyMatch(c -> c.sourceId().equals("ans")));
        assertFalse(chunks.stream().anyMatch(c -> c.sourceId().equals("h2")));

        // AND the MMR observability hook received the in/out counts
        assertEquals(1, observer.calls);
        assertEquals(6, observer.lastFetchK);
        assertEquals(3, observer.lastCandidateCount);
        assertEquals(2, observer.lastSelectedCount);
        assertEquals(0.7, observer.lastLambda);
    }

    @Test
    @DisplayName("with MMR disabled (single-arg constructor), delegates plain dense top-k")
    void mmrDisabledDelegatesPlainTopK() {
        // GIVEN the MMR-disabled wiring
        vectorSearch.setResults(List.of(new KnowledgeChunk("x", "s#1", "support", 0.7)));

        // WHEN retrieving
        service.retrieve("question", "support", 5);

        // THEN the store receives the requested top-k unchanged (no over-fetch)
        assertEquals(5, vectorSearch.lastTopK);
    }

    @Test
    @DisplayName("with query normalization enabled, embeds the greeting-stripped query and observes it")
    void queryNormalizationStripsGreetingBeforeSearch() {
        // GIVEN a service wired with the query normalizer (no MMR)
        FakeRetrievalObserverPort observer = new FakeRetrievalObserverPort();
        KnowledgeRetrievalService normalizing = new KnowledgeRetrievalService(
                vectorSearch, null, observer, 1, new QueryNormalizer());

        // WHEN retrieving a greeting-prefixed question
        normalizing.retrieve("Bonjour, internet est très lent chez moi.", "support", 4);

        // THEN the vector store receives the query without the leading greeting
        assertEquals("internet est très lent chez moi.", vectorSearch.lastQuery);
        // AND the normalization is observed once with the length delta (no MMR call)
        assertEquals(1, observer.normalizeCalls);
        assertEquals("support", observer.lastNormalizeDomain);
        assertEquals(0, observer.calls);
    }

    @Test
    @DisplayName("with query normalization enabled, a greeting-free question is embedded unchanged and not observed")
    void queryNormalizationLeavesPlainQuestionUntouched() {
        // GIVEN a service wired with the query normalizer
        FakeRetrievalObserverPort observer = new FakeRetrievalObserverPort();
        KnowledgeRetrievalService normalizing = new KnowledgeRetrievalService(
                vectorSearch, null, observer, 1, new QueryNormalizer());

        // WHEN retrieving a question with no leading greeting
        normalizing.retrieve("Ma connexion internet est très lente.", "support", 4);

        // THEN the query is passed through verbatim and no normalization event fires
        assertEquals("Ma connexion internet est très lente.", vectorSearch.lastQuery);
        assertEquals(0, observer.normalizeCalls);
    }

    @Test
    @DisplayName("with query normalization disabled (default service), the greeting is embedded as-is")
    void queryNormalizationDisabledKeepsGreeting() {
        // WHEN retrieving a greeting-prefixed question on the default (normalization-off) service
        service.retrieve("Bonjour, internet est très lent chez moi.", "support", 4);

        // THEN the raw query (greeting included) reaches the store
        assertEquals("Bonjour, internet est très lent chez moi.", vectorSearch.lastQuery);
    }
}
