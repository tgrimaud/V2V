package com.voicesupport.knowledge.infrastructure.adapter.out.vectorstore;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.port.out.VectorSearchPort;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;
import com.voicesupport.knowledge.domain.service.TextChunker;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.ai.vectorstore.filter.Filter;
import org.springframework.ai.vectorstore.filter.FilterExpressionBuilder;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class PgVectorStoreAdapter implements VectorStorePort, VectorSearchPort {

    private static final String SHARED_DOMAIN = "general";
    // ADR-0034: the customer answer engine only ever retrieves customer-facing chunks. The filter
    // is fail-closed (chunks without an audience value are excluded), so a full re-sync is required
    // to activate the boundary — see the audience re-sync note in CLAUDE.md.
    private static final String CUSTOMER_AUDIENCE = "customer";

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
        metadata.put("audience", CUSTOMER_AUDIENCE);
        vectorStore.add(List.of(new Document(content, metadata)));
    }

    // Batches all chunks of a document into a single vectorStore.add(...) so Spring AI issues one
    // embedding batch + one multi-row insert instead of one round-trip per chunk (TASK-BE-014).
    @Override
    public int storeChunks(SourceDocument document, List<TextChunker.Chunk> chunks) {
        List<Document> documents = new ArrayList<>(chunks.size());
        for (int chunkIndex = 0; chunkIndex < chunks.size(); chunkIndex++) {
            documents.add(toDocument(document, chunks.get(chunkIndex), chunkIndex));
        }
        if (!documents.isEmpty()) {
            vectorStore.add(documents);
        }
        return documents.size();
    }

    private Document toDocument(SourceDocument document, TextChunker.Chunk chunk, int chunkIndex) {
        Map<String, Object> metadata = new HashMap<>();
        metadata.put("source", document.sourceId());
        metadata.put("section", chunk.section());
        metadata.put("chunk_index", String.valueOf(chunkIndex));
        metadata.put("domain", document.domain());
        metadata.put("audience", document.audience() != null ? document.audience() : CUSTOMER_AUDIENCE);
        metadata.put("source_type", document.sourceType());
        metadata.put("source_id", document.sourceId());
        metadata.put("content_hash", document.contentHash());
        putIfPresent(metadata, "title", document.title());
        putIfPresent(metadata, "url", document.url());
        putIfPresent(metadata, "language", document.language());
        if (document.updatedAt() != null) {
            metadata.put("updated_at", document.updatedAt().toString());
        }
        return new Document(chunk.content(), metadata);
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
        SearchRequest.Builder request = SearchRequest.builder()
                .query(query).topK(topK)
                .filterExpression(buildSearchFilter(domain));
        List<Document> documents = vectorStore.similaritySearch(request.build());
        return documents == null ? List.of() : documents.stream().map(this::toChunk).toList();
    }

    // ADR-0034: always restrict the customer answer engine to customer-facing chunks (fail-closed),
    // AND-combined with the optional domain restriction. Internal/agent-desk content (BUG-005) is
    // therefore never retrievable here regardless of the requested domain.
    private Filter.Expression buildSearchFilter(String domain) {
        FilterExpressionBuilder fb = new FilterExpressionBuilder();
        FilterExpressionBuilder.Op customer = fb.eq("audience", CUSTOMER_AUDIENCE);
        FilterExpressionBuilder.Op domainOp = domainOp(fb, domain);
        return (domainOp == null ? customer : fb.and(customer, domainOp)).build();
    }

    // Restrict to the requested domain plus the shared "general" domain. A null/blank domain means
    // no domain restriction; an explicit "general" resolves to the shared domain only.
    private FilterExpressionBuilder.Op domainOp(FilterExpressionBuilder fb, String domain) {
        if (domain == null || domain.isBlank()) {
            return null;
        }
        if (SHARED_DOMAIN.equals(domain)) {
            return fb.eq("domain", SHARED_DOMAIN);
        }
        return fb.or(fb.eq("domain", domain), fb.eq("domain", SHARED_DOMAIN));
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
