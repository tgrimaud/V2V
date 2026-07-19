package com.voicesupport.knowledge.infrastructure.adapter.out.vectorstore;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.port.out.VectorSearchPort;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.ai.vectorstore.filter.Filter;
import org.springframework.ai.vectorstore.filter.FilterExpressionBuilder;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class PgVectorStoreAdapter implements VectorStorePort, VectorSearchPort {

    private static final String SHARED_DOMAIN = "general";

    private final VectorStore vectorStore;

    public PgVectorStoreAdapter(VectorStore vectorStore) {
        this.vectorStore = vectorStore;
    }

    // One-shot ingest path: stores content without source_type/source_id, so these chunks
    // are intentionally outside the sync deletion-diff lifecycle (manual, ad-hoc content).
    @Override
    public void store(String content, String source, String section, int chunkIndex, String domain) {
        Map<String, Object> metadata = new HashMap<>();
        metadata.put("source", source);
        metadata.put("section", section);
        metadata.put("chunk_index", String.valueOf(chunkIndex));
        metadata.put("domain", domain != null ? domain : SHARED_DOMAIN);
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

    @Override
    public List<KnowledgeChunk> search(String query, String domain, int topK) {
        SearchRequest.Builder request = SearchRequest.builder().query(query).topK(topK);
        Filter.Expression domainFilter = buildDomainFilter(domain);
        if (domainFilter != null) {
            request.filterExpression(domainFilter);
        }
        List<Document> documents = vectorStore.similaritySearch(request.build());
        return documents == null ? List.of() : documents.stream().map(this::toChunk).toList();
    }

    // Restrict results to the requested domain plus the shared "general" domain.
    // A null/blank domain means no domain restriction (search the whole store).
    // An explicit "general" resolves to the shared domain only (never cross-domain).
    private Filter.Expression buildDomainFilter(String domain) {
        if (domain == null || domain.isBlank()) {
            return null;
        }
        FilterExpressionBuilder fb = new FilterExpressionBuilder();
        if (SHARED_DOMAIN.equals(domain)) {
            return fb.eq("domain", SHARED_DOMAIN).build();
        }
        return fb.or(fb.eq("domain", domain), fb.eq("domain", SHARED_DOMAIN)).build();
    }

    private KnowledgeChunk toChunk(Document document) {
        Object domain = document.getMetadata().get("domain");
        Object sourceId = document.getMetadata().get("source_id");
        Object source = document.getMetadata().get("source");
        String resolvedSource = sourceId != null ? sourceId.toString()
                : (source != null ? source.toString() : null);
        Double score = document.getScore();
        return new KnowledgeChunk(
                document.getText(),
                resolvedSource,
                domain != null ? domain.toString() : SHARED_DOMAIN,
                score != null ? score : 0.0);
    }

    private void putIfPresent(Map<String, Object> metadata, String key, String value) {
        if (value != null && !value.isBlank()) {
            metadata.put(key, value);
        }
    }
}
