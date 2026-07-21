package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
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

    @Override
    public void store(String content, String source, String section, int chunkIndex, String domain) {
        storedChunks.add(source + "#" + chunkIndex + "[" + domain + "]");
        storedChunkDomains.add(domain);
        storedChunkContents.add(content);
    }

    @Override
    public int storeChunks(SourceDocument document, List<TextChunker.Chunk> chunks) {
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
        return chunks.size();
    }

    @Override
    public void deleteBySource(String sourceType, String sourceId) {
        deletedSources.add(sourceType + "/" + sourceId);
    }
}
