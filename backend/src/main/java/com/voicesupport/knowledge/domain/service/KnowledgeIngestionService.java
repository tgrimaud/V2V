package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;

import java.util.List;

public class KnowledgeIngestionService implements IngestKnowledgeUseCase {

    private final VectorStorePort vectorStorePort;
    private final TextChunker textChunker;

    public KnowledgeIngestionService(VectorStorePort vectorStorePort, TextChunker textChunker) {
        this.vectorStorePort = vectorStorePort;
        this.textChunker = textChunker;
    }

    @Override
    public int ingest(String content, String sourceName) {
        return ingest(content, sourceName, null);
    }

    @Override
    public int ingest(String content, String sourceName, String domain) {
        List<TextChunker.Chunk> chunks = textChunker.chunk(content);
        int chunkIndex = 0;
        for (TextChunker.Chunk chunk : chunks) {
            vectorStorePort.store(chunk.content(), sourceName, chunk.section(), chunkIndex++, domain);
        }
        return chunks.size();
    }
}
