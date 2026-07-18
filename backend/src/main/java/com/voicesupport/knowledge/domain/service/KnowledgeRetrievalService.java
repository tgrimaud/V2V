package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import com.voicesupport.knowledge.domain.port.out.VectorSearchPort;

import java.util.List;

public class KnowledgeRetrievalService implements KnowledgeRetrievalUseCase {

    private static final int DEFAULT_TOP_K = 4;

    private final VectorSearchPort vectorSearchPort;

    public KnowledgeRetrievalService(VectorSearchPort vectorSearchPort) {
        this.vectorSearchPort = vectorSearchPort;
    }

    @Override
    public List<KnowledgeChunk> retrieve(String query, String domain, int topK) {
        if (query == null || query.isBlank()) {
            return List.of();
        }
        return vectorSearchPort.search(query, normalizeDomain(domain), effectiveTopK(topK));
    }

    private int effectiveTopK(int topK) {
        return topK > 0 ? topK : DEFAULT_TOP_K;
    }

    private String normalizeDomain(String domain) {
        return domain != null && !domain.isBlank() ? domain : null;
    }
}
