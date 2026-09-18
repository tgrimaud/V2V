package com.voicesupport.knowledge.infrastructure.adapter.out.vectorstore;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.port.out.VectorSearchPort;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;
import com.voicesupport.knowledge.domain.service.TextChunker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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

    private static final Logger log = LoggerFactory.getLogger(PgVectorStoreAdapter.class);

    private static final String SHARED_DOMAIN = "general";
    // ADR-0034: the customer answer engine only ever retrieves customer-facing chunks. The filter
    // is fail-closed (chunks without an audience value are excluded), so a full re-sync is required
    // to activate the boundary — see the audience re-sync note in CLAUDE.md.
    private static final String CUSTOMER_AUDIENCE = "customer";
    // BUG-022: cap chunks per embedding request. A whole document used to be embedded in one
    // vectorStore.add(...), so a large article (hundreds of chunks) produced one huge embedding
    // call the client's per-read timeout could not bound (it fires on a read gap, not overall) —
    // a single slow/hung batch stalled the entire corpus sync indefinitely. Small bounded batches
    // keep each request short enough for the timeout to bite, so a bad batch fails fast and is
    // skipped instead of hanging.
    private static final int DEFAULT_STORE_BATCH_SIZE = 32;

    private final VectorStore vectorStore;
    private final int storeBatchSize;

    public PgVectorStoreAdapter(VectorStore vectorStore) {
        this(vectorStore, DEFAULT_STORE_BATCH_SIZE);
    }

    public PgVectorStoreAdapter(VectorStore vectorStore, int storeBatchSize) {
        this.vectorStore = vectorStore;
        this.storeBatchSize = storeBatchSize > 0 ? storeBatchSize : DEFAULT_STORE_BATCH_SIZE;
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

    // Stores a document's chunks in bounded batches (TASK-BE-014 kept the one-embedding-call-per-batch
    // efficiency; BUG-022 caps the batch size so no single request can stall the sync). Blank chunks
    // are dropped (never embed empty content) and a batch that still fails/times out is skipped and
    // logged instead of aborting or hanging the whole corpus sync. Returns the count actually stored.
    @Override
    public int storeChunks(SourceDocument document, List<TextChunker.Chunk> chunks) {
        List<Document> documents = toDocuments(document, chunks);
        int stored = 0;
        for (int from = 0; from < documents.size(); from += storeBatchSize) {
            int to = Math.min(from + storeBatchSize, documents.size());
            stored += storeBatch(document, documents.subList(from, to));
        }
        return stored;
    }

    private List<Document> toDocuments(SourceDocument document, List<TextChunker.Chunk> chunks) {
        List<Document> documents = new ArrayList<>(chunks.size());
        for (TextChunker.Chunk chunk : chunks) {
            if (chunk.content() == null || chunk.content().isBlank()) {
                continue; // BUG-022: a blank chunk carries no signal and can hang the embedder
            }
            documents.add(toDocument(document, chunk, documents.size()));
        }
        return documents;
    }

    private int storeBatch(SourceDocument document, List<Document> batch) {
        try {
            vectorStore.add(batch);
            return batch.size();
        } catch (RuntimeException failure) {
            log.warn("[KB-SYNC] skipped embedding batch source_type={} source_id={} skipped_chunks={} error_code={}",
                    document.sourceType(), document.sourceId(), batch.size(), failure.getClass().getSimpleName());
            return 0;
        }
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
