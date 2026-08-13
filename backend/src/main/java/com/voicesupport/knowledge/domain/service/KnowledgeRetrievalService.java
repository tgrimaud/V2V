package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import com.voicesupport.knowledge.domain.port.out.RetrievalObserverPort;
import com.voicesupport.knowledge.domain.port.out.VectorSearchPort;

import java.util.List;

public class KnowledgeRetrievalService implements KnowledgeRetrievalUseCase {

    private static final int DEFAULT_TOP_K = 4;

    private final VectorSearchPort vectorSearchPort;
    // null => MMR disabled: plain dense top-k, preserving the pre-TASK-BE-028 behaviour.
    private final MmrReranker mmrReranker;
    private final RetrievalObserverPort observer;
    private final int fetchMultiplier;
    // null => query normalization disabled (TASK-BE-029): the raw query is embedded as-is.
    private final QueryNormalizer queryNormalizer;

    // MMR-disabled wiring (also used by tests): plain dense top-k, no query normalization.
    public KnowledgeRetrievalService(VectorSearchPort vectorSearchPort) {
        this(vectorSearchPort, null, NoopRetrievalObserver.INSTANCE, 1, null);
    }

    // MMR-enabled wiring (TASK-BE-028) without query normalization (kept for existing tests).
    public KnowledgeRetrievalService(
            VectorSearchPort vectorSearchPort, MmrReranker mmrReranker,
            RetrievalObserverPort observer, int fetchMultiplier) {
        this(vectorSearchPort, mmrReranker, observer, fetchMultiplier, null);
    }

    // Master wiring. mmrReranker=null keeps plain dense top-k (over-fetch topK*fetchMultiplier then
    // greedily re-select topK when set, TASK-BE-028); queryNormalizer=null keeps the raw embedding
    // query (strip a leading greeting before search when set, TASK-BE-029). fetchMultiplier is
    // floored at 1 (no over-fetch).
    public KnowledgeRetrievalService(
            VectorSearchPort vectorSearchPort, MmrReranker mmrReranker,
            RetrievalObserverPort observer, int fetchMultiplier, QueryNormalizer queryNormalizer) {
        this.vectorSearchPort = vectorSearchPort;
        this.mmrReranker = mmrReranker;
        this.observer = observer != null ? observer : NoopRetrievalObserver.INSTANCE;
        this.fetchMultiplier = Math.max(1, fetchMultiplier);
        this.queryNormalizer = queryNormalizer;
    }

    @Override
    public List<KnowledgeChunk> retrieve(String query, String domain, int topK) {
        if (query == null || query.isBlank()) {
            return List.of();
        }
        int finalK = effectiveTopK(topK);
        String normalizedDomain = normalizeDomain(domain);
        String searchQuery = normalizeQuery(query, normalizedDomain);
        if (mmrReranker == null) {
            return vectorSearchPort.search(searchQuery, normalizedDomain, finalK);
        }
        int fetchK = finalK * fetchMultiplier;
        List<KnowledgeChunk> candidates = vectorSearchPort.search(searchQuery, normalizedDomain, fetchK);
        List<KnowledgeChunk> selected = mmrReranker.rerank(candidates, finalK);
        observer.mmrApplied(normalizedDomain, fetchK, candidates.size(), selected.size(), mmrReranker.lambda());
        return selected;
    }

    private String normalizeQuery(String query, String normalizedDomain) {
        if (queryNormalizer == null) {
            return query;
        }
        String rewritten = queryNormalizer.normalize(query);
        if (!rewritten.equals(query)) {
            observer.queryNormalized(normalizedDomain, query.length(), rewritten.length());
        }
        return rewritten;
    }

    private int effectiveTopK(int topK) {
        return topK > 0 ? topK : DEFAULT_TOP_K;
    }

    private String normalizeDomain(String domain) {
        return domain != null && !domain.isBlank() ? domain : null;
    }
}
