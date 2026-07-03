package com.voicesupport.infrastructure.adapter.out.vectorstore;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.SourceDocument;
import com.voicesupport.domain.port.out.VectorSearchPort;
import com.voicesupport.domain.port.out.VectorStorePort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.ai.vectorstore.filter.Filter;
import org.springframework.ai.vectorstore.filter.FilterExpressionBuilder;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class PgVectorStoreAdapter implements VectorStorePort, VectorSearchPort {

    private static final Logger log = LoggerFactory.getLogger(PgVectorStoreAdapter.class);

    private final VectorStore vectorStore;

    public PgVectorStoreAdapter(VectorStore vectorStore) {
        this.vectorStore = vectorStore;
    }

    @Override
    public void store(String content, String source, String section, int chunkIndex) {
        store(content, source, section, chunkIndex, null);
    }

    @Override
    public void store(String content, String source, String section, int chunkIndex, String domain) {
        Map<String, Object> metadata = new HashMap<>(Map.of(
                "source", source,
                "section", section,
                "chunk_index", String.valueOf(chunkIndex),
                "domain", domain != null ? domain : "general"
        ));
        Document document = new Document(content, metadata);
        vectorStore.add(List.of(document));
    }

    @Override
    public void storeChunk(SourceDocument source, String chunkContent, String section, int chunkIndex) {
        Map<String, Object> metadata = new HashMap<>();
        metadata.put("source", source.sourceId());
        metadata.put("section", section);
        metadata.put("chunk_index", String.valueOf(chunkIndex));
        metadata.put("domain", source.domain());
        metadata.put("source_type", source.sourceType());
        metadata.put("source_id", source.sourceId());
        metadata.put("content_hash", source.contentHash());
        putIfPresent(metadata, "title", source.title());
        putIfPresent(metadata, "url", source.url());
        putIfPresent(metadata, "language", source.language());
        if (source.updatedAt() != null) {
            metadata.put("updated_at", source.updatedAt().toString());
        }
        vectorStore.add(List.of(new Document(chunkContent, metadata)));
    }

    @Override
    public void deleteBySource(String sourceType, String sourceId) {
        FilterExpressionBuilder fb = new FilterExpressionBuilder();
        Filter.Expression filter = fb.and(
                fb.eq("source_type", sourceType),
                fb.eq("source_id", sourceId)
        ).build();
        vectorStore.delete(filter);
    }

    private void putIfPresent(Map<String, Object> metadata, String key, String value) {
        if (value != null && !value.isBlank()) {
            metadata.put(key, value);
        }
    }

    @Override
    public List<Citation> searchRelevant(String query, int topK) {
        return searchRelevant(query, topK, null);
    }

    @Override
    public List<Citation> searchRelevant(String query, int topK, String domain) {
        SearchRequest.Builder builder = SearchRequest.builder()
                .query(query)
                .topK(topK)
                .similarityThreshold(0.5);

        if (domain != null) {
            FilterExpressionBuilder fb = new FilterExpressionBuilder();
            builder.filterExpression(
                    fb.or(fb.eq("domain", domain), fb.eq("domain", "general")).build()
            );
        }

        long startNanos = System.nanoTime();
        List<Document> found = vectorStore.similaritySearch(builder.build());
        List<Document> results = found != null ? found : List.of();
        long elapsedMs = (System.nanoTime() - startNanos) / 1_000_000;
        log.info("[LATENCY] step=vector_search ms={} top_k={} domain={} results={}",
                elapsedMs, topK, domain != null ? domain : "all", results.size());

        return results.stream()
                .map(doc -> new Citation(
                        getMetadata(doc, "source"),
                        getMetadata(doc, "section"),
                        doc.getText(),
                        doc.getScore() != null ? doc.getScore() : 0.0
                ))
                .toList();
    }

    private String getMetadata(Document doc, String key) {
        Object value = doc.getMetadata().get(key);
        return value != null ? value.toString() : "unknown";
    }
}
