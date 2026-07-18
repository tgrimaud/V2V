package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.port.out.VectorSearchPort;

import java.util.ArrayList;
import java.util.List;

public class FakeVectorSearchPort implements VectorSearchPort {

    private final List<KnowledgeChunk> results = new ArrayList<>();

    public String lastQuery;
    public String lastDomain;
    public int lastTopK;
    public int callCount;

    public void setResults(List<KnowledgeChunk> chunks) {
        this.results.clear();
        this.results.addAll(chunks);
    }

    @Override
    public List<KnowledgeChunk> search(String query, String domain, int topK) {
        this.lastQuery = query;
        this.lastDomain = domain;
        this.lastTopK = topK;
        this.callCount++;
        return results.stream().limit(topK).toList();
    }
}
