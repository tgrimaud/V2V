package com.voicesupport.knowledge.domain.port.out;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import java.util.List;

public interface VectorSearchPort {

    // Returns the top-k most similar chunks. Implementations restrict results to the
    // requested domain plus the shared "general" domain (domain == X OR general).
    // A null/blank domain means no domain restriction.
    List<KnowledgeChunk> search(String query, String domain, int topK);
}
