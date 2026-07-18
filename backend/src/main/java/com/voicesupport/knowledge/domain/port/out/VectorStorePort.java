package com.voicesupport.knowledge.domain.port.out;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;

public interface VectorStorePort {

    void store(String content, String source, String section, int chunkIndex, String domain);

    void storeChunk(SourceDocument document, String chunkContent, String section, int chunkIndex);

    void deleteBySource(String sourceType, String sourceId);
}
