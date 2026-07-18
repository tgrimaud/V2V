package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;

import java.util.ArrayList;
import java.util.List;

public class FakeVectorStorePort implements VectorStorePort {

    public final List<String> storedChunks = new ArrayList<>();
    public final List<String> deletedSources = new ArrayList<>();

    @Override
    public void store(String content, String source, String section, int chunkIndex, String domain) {
        storedChunks.add(source + "#" + chunkIndex + "[" + domain + "]");
    }

    @Override
    public void storeChunk(SourceDocument document, String chunkContent, String section, int chunkIndex) {
        storedChunks.add(document.sourceType() + "/" + document.sourceId() + "#" + chunkIndex);
    }

    @Override
    public void deleteBySource(String sourceType, String sourceId) {
        deletedSources.add(sourceType + "/" + sourceId);
    }
}
