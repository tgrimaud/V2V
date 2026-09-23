package com.voicesupport.knowledge.infrastructure.adapter.out.vectorstore;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.model.valueobject.StoreResult;
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
    // TASK-BE-034 (ADR-0048): fail-open sentinel written on every chunk that has no language, so the
    // language filter can keep untagged content retrievable in every language via
    // (language == requestLanguage OR language == unspecified). Mirrors the domain "general" leg —
    // the pgvector jsonpath filter cannot express "metadata key absent", so a stored sentinel value
    // is used instead. Activating the filter therefore requires a full re-sync (like audience).
    private static final String LANGUAGE_UNSPECIFIED = "und";
    // BUG-022: cap chunks per embedding request. A whole document used to be embedded in one
    // vectorStore.add(...), so a large article (hundreds of chunks) produced one huge embedding
    // call the client's per-read timeout could not bound (it fires on a read gap, not overall) —
    // a single slow/hung batch stalled the entire corpus sync indefinitely. Small bounded batches
    // keep each request short enough for the timeout to bite, so a bad batch fails fast and is
    // skipped instead of hanging.
    private static final int DEFAULT_STORE_BATCH_SIZE = 32;

    private final VectorStore vectorStore;
    private final int storeBatchSize;
    // TASK-BE-034: off by default so a single-corpus deployment keeps today's cross-language
    // behaviour; enabled per deployment once both corpora are loaded and re-synced.
    private final boolean languageFilterEnabled;

    public PgVectorStoreAdapter(VectorStore vectorStore) {
        this(vectorStore, DEFAULT_STORE_BATCH_SIZE);
    }

    public PgVectorStoreAdapter(VectorStore vectorStore, int storeBatchSize) {
        this(vectorStore, storeBatchSize, false);
    }

    public PgVectorStoreAdapter(VectorStore vectorStore, int storeBatchSize, boolean languageFilterEnabled) {
        this.vectorStore = vectorStore;
        this.storeBatchSize = storeBatchSize > 0 ? storeBatchSize : DEFAULT_STORE_BATCH_SIZE;
        this.languageFilterEnabled = languageFilterEnabled;
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
        // TASK-BE-034: ad-hoc one-shot content has no language, so tag it unspecified to stay
        // retrievable in every language once the language filter is enabled (fail-open).
        metadata.put("language", LANGUAGE_UNSPECIFIED);
        vectorStore.add(List.of(new Document(content, metadata)));
    }

    // Stores a document's chunks in bounded batches (TASK-BE-014 kept the one-embedding-call-per-batch
    // efficiency; BUG-022 caps the batch size so no single request can stall the sync). Blank chunks
    // are dropped (never embed empty content) and a batch that still fails/times out is skipped and
    // logged instead of aborting or hanging the whole corpus sync. Returns the count actually stored.
    @Override
    public StoreResult storeChunks(SourceDocument document, List<TextChunker.Chunk> chunks) {
        List<Document> documents = toDocuments(document, chunks);
        int stored = 0;
        for (int from = 0; from < documents.size(); from += storeBatchSize) {
            int to = Math.min(from + storeBatchSize, documents.size());
            stored += storeBatch(document, documents.subList(from, to));
        }
        return StoreResult.of(stored, documents.size());
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
        // TASK-BE-034: always store a language (fail-open sentinel when the source has none) so the
        // language filter's (== requestLanguage OR == unspecified) leg keeps untagged content reachable.
        metadata.put("language", hasText(document.language()) ? document.language() : LANGUAGE_UNSPECIFIED);
        putIfPresent(metadata, "title", document.title());
        putIfPresent(metadata, "url", document.url());
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
    public List<KnowledgeChunk> search(String query, String domain, String language, int topK) {
        SearchRequest.Builder request = SearchRequest.builder()
                .query(query).topK(topK)
                .filterExpression(buildSearchFilter(domain, language));
        List<Document> documents = vectorStore.similaritySearch(request.build());
        return documents == null ? List.of() : documents.stream().map(this::toChunk).toList();
    }

    // ADR-0034: always restrict the customer answer engine to customer-facing chunks (fail-closed),
    // AND-combined with the optional domain and language restrictions. Internal/agent-desk content
    // (BUG-005) is therefore never retrievable here regardless of the requested domain/language.
    private Filter.Expression buildSearchFilter(String domain, String language) {
        FilterExpressionBuilder fb = new FilterExpressionBuilder();
        FilterExpressionBuilder.Op filter = fb.eq("audience", CUSTOMER_AUDIENCE);
        filter = and(fb, filter, domainOp(fb, domain));
        filter = and(fb, filter, languageOp(fb, language));
        return filter.build();
    }

    private FilterExpressionBuilder.Op and(
            FilterExpressionBuilder fb, FilterExpressionBuilder.Op left, FilterExpressionBuilder.Op right) {
        return right == null ? left : fb.and(left, right);
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

    // TASK-BE-034 (ADR-0048): restrict to the request language plus the unspecified sentinel, so a
    // bilingual store no longer mixes FR and EN chunks in the same top-K while untagged content stays
    // reachable (fail-open on the language axis, unlike the fail-closed audience axis). Off unless the
    // filter is enabled; a null/blank request language means no language restriction (backward-compatible).
    private FilterExpressionBuilder.Op languageOp(FilterExpressionBuilder fb, String language) {
        if (!languageFilterEnabled || !hasText(language)) {
            return null;
        }
        return fb.or(fb.eq("language", language), fb.eq("language", LANGUAGE_UNSPECIFIED));
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
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
