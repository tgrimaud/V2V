package com.voicesupport.infrastructure.adapter.out.vectorstore;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.port.out.VectorSearchPort;
import com.voicesupport.domain.port.out.VectorStorePort;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.ai.vectorstore.filter.FilterExpressionBuilder;

import java.util.List;
import java.util.Map;

public class PgVectorStoreAdapter implements VectorStorePort, VectorSearchPort {

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
        Map<String, Object> metadata = new java.util.HashMap<>(Map.of(
                "source", source,
                "section", section,
                "chunk_index", String.valueOf(chunkIndex),
                "domain", domain != null ? domain : "general"
        ));
        Document document = new Document(content, metadata);
        vectorStore.add(List.of(document));
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

        List<Document> results = vectorStore.similaritySearch(builder.build());

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
