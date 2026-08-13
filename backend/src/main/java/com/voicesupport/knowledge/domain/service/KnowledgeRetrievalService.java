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

    // MMR-disabled wiring (also used by tests): plain dense top-k.
    public KnowledgeRetrievalService(VectorSearchPort vectorSearchPort) {
        this(vectorSearchPort, null, RetrievalObserverPort.NOOP, 1);
    }

    // MMR-enabled wiring (TASK-BE-028): over-fetch topK * fetchMultiplier dense candidates, then
    // greedily re-select topK balancing relevance against redundancy so near-duplicate chunks stop
    // evicting the answer chunk (BUG-003). fetchMultiplier is floored at 1 (no over-fetch).
    public KnowledgeRetrievalService(
            VectorSearchPort vectorSearchPort, MmrReranker mmrReranker,
            RetrievalObserverPort observer, int fetchMultiplier) {
        this.vectorSearchPort = vectorSearchPort;
        this.mmrReranker = mmrReranker;
        this.observer = observer != null ? observer : RetrievalObserverPort.NOOP;
        this.fetchMultiplier = Math.max(1, fetchMultiplier);
    }

    @Override
    public List<KnowledgeChunk> retrieve(String query, String domain, int topK) {
        if (query == null || query.isBlank()) {
            return List.of();
        }
        int finalK = effectiveTopK(topK);
        String normalizedDomain = normalizeDomain(domain);
        if (mmrReranker == null) {
            return vectorSearchPort.search(query, normalizedDomain, finalK);
        }
        int fetchK = finalK * fetchMultiplier;
        List<KnowledgeChunk> candidates = vectorSearchPort.search(query, normalizedDomain, fetchK);
        List<KnowledgeChunk> selected = mmrReranker.rerank(candidates, finalK);
        observer.mmrApplied(normalizedDomain, fetchK, candidates.size(), selected.size(), mmrReranker.lambda());
        return selected;
    }

    private int effectiveTopK(int topK) {
        return topK > 0 ? topK : DEFAULT_TOP_K;
    }

    private String normalizeDomain(String domain) {
        return domain != null && !domain.isBlank() ? domain : null;
    }
}
