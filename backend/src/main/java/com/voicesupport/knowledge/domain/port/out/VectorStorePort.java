package com.voicesupport.knowledge.domain.port.out;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.model.valueobject.StoreResult;
import com.voicesupport.knowledge.domain.service.TextChunker;

import java.util.List;

public interface VectorStorePort {

    void store(String content, String source, String section, int chunkIndex, String domain);

    // Stores a document's chunks in bounded batches (TASK-BE-014 efficiency; BUG-022 caps the batch
    // size so no single request can stall the sync). Blank chunks are dropped and a batch that
    // fails/times out is skipped, so the count actually stored can be < chunks.size(). Returns a
    // StoreResult(stored, attempted) so the caller can tell a complete document from a partial one.
    StoreResult storeChunks(SourceDocument document, List<TextChunker.Chunk> chunks);

    void deleteBySource(String sourceType, String sourceId);
}
