package com.voicesupport.knowledge.domain.port.in;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import java.util.List;

public interface KnowledgeRetrievalUseCase {

    List<KnowledgeChunk> retrieve(String query, String domain, int topK);
}
