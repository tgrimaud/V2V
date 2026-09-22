package com.voicesupport.knowledge.domain.port.out;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import java.util.List;

public interface VectorSearchPort {

    // Returns the top-k most similar chunks. Implementations restrict results to the
    // requested domain plus the shared "general" domain (domain == X OR general).
    // A null/blank domain means no domain restriction. When the language filter is
    // enabled (TASK-BE-034, ADR-0048), a non-blank language restricts results to that
    // language plus untagged/unspecified chunks (language == X OR unspecified); a
    // null/blank language means no language restriction (backward-compatible).
    List<KnowledgeChunk> search(String query, String domain, String language, int topK);
}
