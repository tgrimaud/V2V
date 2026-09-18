package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.model.valueobject.StoreResult;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;
import com.voicesupport.knowledge.domain.service.TextChunker;

import java.util.ArrayList;
import java.util.List;

public class FakeVectorStorePort implements VectorStorePort {

    public final List<String> storedChunks = new ArrayList<>();
    public final List<String> storedChunkDomains = new ArrayList<>();
    public final List<String> storedChunkContents = new ArrayList<>();
    public final List<String> deletedSources = new ArrayList<>();
    // Counts storeChunks(...) invocations so tests can assert one batched call per document.
    public int storeChunksCalls = 0;
    // When set, storeChunks throws for this sourceId to exercise the fail-fast / failure-observability path.
    public String failOnSourceId = null;
    // When set, storeChunks returns a PARTIAL StoreResult (stored < attempted) for this sourceId to
    // exercise the BUG-022 incomplete-not-committed path (a sub-batch was skipped after a timeout).
    public String partialOnSourceId = null;
    public int partialStored = 0;

    @Override
    public void store(String content, String source, String section, int chunkIndex, String domain) {
        storedChunks.add(source + "#" + chunkIndex + "[" + domain + "]");
        storedChunkDomains.add(domain);
        storedChunkContents.add(content);
    }

    @Override
    public StoreResult storeChunks(SourceDocument document, List<TextChunker.Chunk> chunks) {
        storeChunksCalls++;
        if (document.sourceId().equals(failOnSourceId)) {
            throw new IllegalStateException("vector store write failed for " + document.sourceId());
        }
        for (int chunkIndex = 0; chunkIndex < chunks.size(); chunkIndex++) {
            TextChunker.Chunk chunk = chunks.get(chunkIndex);
            storedChunks.add(document.sourceType() + "/" + document.sourceId() + "#" + chunkIndex);
            storedChunkDomains.add(document.domain());
            storedChunkContents.add(chunk.content());
        }
        if (document.sourceId().equals(partialOnSourceId)) {
            return StoreResult.of(partialStored, chunks.size());
        }
        return StoreResult.of(chunks.size(), chunks.size());
    }

    @Override
    public void deleteBySource(String sourceType, String sourceId) {
        deletedSources.add(sourceType + "/" + sourceId);
    }
}
