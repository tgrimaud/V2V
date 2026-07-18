package com.voicesupport.conversation.fake;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import java.util.ArrayList;
import java.util.List;

public class FakeKnowledgeRetrievalUseCase implements KnowledgeRetrievalUseCase {

    private final List<KnowledgeChunk> chunks = new ArrayList<>();

    public void setChunks(List<KnowledgeChunk> chunks) {
        this.chunks.clear();
        this.chunks.addAll(chunks);
    }

    @Override
    public List<KnowledgeChunk> retrieve(String query, String domain, int topK) {
        return chunks.stream().limit(topK).toList();
    }
}
