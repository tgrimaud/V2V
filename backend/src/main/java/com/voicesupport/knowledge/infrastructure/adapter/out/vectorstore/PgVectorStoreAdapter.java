package com.voicesupport.knowledge.infrastructure.adapter.out.vectorstore;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.ai.vectorstore.filter.Filter;
import org.springframework.ai.vectorstore.filter.FilterExpressionBuilder;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class PgVectorStoreAdapter implements VectorStorePort {

    private final VectorStore vectorStore;

    public PgVectorStoreAdapter(VectorStore vectorStore) {
        this.vectorStore = vectorStore;
    }

    @Override
    public void store(String content, String source, String section, int chunkIndex, String domain) {
        Map<String, Object> metadata = new HashMap<>();
        metadata.put("source", source);
        metadata.put("section", section);
        metadata.put("chunk_index", String.valueOf(chunkIndex));
        metadata.put("domain", domain != null ? domain : "general");
        vectorStore.add(List.of(new Document(content, metadata)));
    }

    @Override
    public void storeChunk(SourceDocument document, String chunkContent, String section, int chunkIndex) {
        Map<String, Object> metadata = new HashMap<>();
        metadata.put("source", document.sourceId());
        metadata.put("section", section);
        metadata.put("chunk_index", String.valueOf(chunkIndex));
        metadata.put("domain", document.domain());
        metadata.put("source_type", document.sourceType());
        metadata.put("source_id", document.sourceId());
        metadata.put("content_hash", document.contentHash());
        putIfPresent(metadata, "title", document.title());
        putIfPresent(metadata, "url", document.url());
        putIfPresent(metadata, "language", document.language());
        if (document.updatedAt() != null) {
            metadata.put("updated_at", document.updatedAt().toString());
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
}
