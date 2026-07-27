package com.voicesupport.knowledge.infrastructure.adapter.out.vectorstore;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.service.TextChunker;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.ai.vectorstore.filter.Filter;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("PgVectorStoreAdapter — audience boundary (ADR-0034 / BUG-005)")
class PgVectorStoreAdapterTest {

    private final CapturingVectorStore vectorStore = new CapturingVectorStore();
    private final PgVectorStoreAdapter adapter = new PgVectorStoreAdapter(vectorStore);

    @Test
    @DisplayName("search always restricts to the customer audience, even with no domain")
    void searchAlwaysRestrictsToCustomerAudience() {
        adapter.search("why did my bill increase", null, 5);

        String filter = requireFilter();
        assertTrue(filter.contains("audience"), filter);
        assertTrue(filter.contains("customer"), filter);
    }

    @Test
    @DisplayName("search AND-combines the customer audience with the domain restriction")
    void searchCombinesAudienceAndDomain() {
        adapter.search("why did my bill increase", "billing", 5);

        String filter = requireFilter();
        assertTrue(filter.contains("audience") && filter.contains("customer"), filter);
        assertTrue(filter.contains("billing"), filter);
        assertTrue(filter.contains("general"), filter);
    }

    @Test
    @DisplayName("stored chunks carry the document audience so internal content is tagged for exclusion")
    void storedChunksCarryAudienceMetadata() {
        SourceDocument internal = SourceDocument.create(
                "csv-article", "253", "VAA", null, "Modify the appointment in R6/ION.",
                "support", "internal", "en", Instant.now());

        adapter.storeChunks(internal, List.of(new TextChunker.Chunk("Modify the appointment in R6/ION.", "VAA")));

        assertEquals(1, vectorStore.added.size());
        assertEquals("internal", vectorStore.added.get(0).getMetadata().get("audience"));
    }

    @Test
    @DisplayName("one-shot store defaults chunks to the customer audience")
    void oneShotStoreDefaultsToCustomerAudience() {
        adapter.store("Your bill can change when a discount ends.", "kb", "billing", 0, "billing");

        assertEquals(1, vectorStore.added.size());
        assertEquals("customer", vectorStore.added.get(0).getMetadata().get("audience"));
    }

    private String requireFilter() {
        assertNotNull(vectorStore.lastRequest, "similaritySearch was not invoked");
        Filter.Expression expression = vectorStore.lastRequest.getFilterExpression();
        assertNotNull(expression, "no filter expression was applied");
        return expression.toString();
    }

    // Minimal Spring AI VectorStore fake: captures the search request + added documents so the
    // audience filter and the stored audience metadata can be asserted without a real pgvector.
    private static final class CapturingVectorStore implements VectorStore {
        private SearchRequest lastRequest;
        private final List<Document> added = new ArrayList<>();

        @Override
        public void add(List<Document> documents) {
            added.addAll(documents);
        }

        @Override
        public void delete(List<String> idList) {
        }

        @Override
        public void delete(Filter.Expression filterExpression) {
        }

        @Override
        public List<Document> similaritySearch(SearchRequest request) {
            this.lastRequest = request;
            return List.of();
        }
    }
}
