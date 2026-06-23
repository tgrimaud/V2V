package com.voicesupport.domain.port.out;

import com.voicesupport.domain.model.SourceDocument;

public interface VectorStorePort {

    void store(String content, String source, String section, int chunkIndex);

    void store(String content, String source, String section, int chunkIndex, String domain);

    void storeChunk(SourceDocument document, String chunkContent, String section, int chunkIndex);

    void deleteBySource(String sourceType, String sourceId);
}
