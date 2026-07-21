package com.voicesupport.knowledge.domain.port.out;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.service.TextChunker;

import java.util.List;

public interface VectorStorePort {

    void store(String content, String source, String section, int chunkIndex, String domain);

    // Stores all chunks of a document in a single batched operation (one embedding + insert call
    // instead of one per chunk) so a bulk corpus sync stays viable (TASK-BE-014).
    // Returns the number of chunks stored (== chunks.size()). chunkIndex is the list position.
    int storeChunks(SourceDocument document, List<TextChunker.Chunk> chunks);

    void deleteBySource(String sourceType, String sourceId);
}
