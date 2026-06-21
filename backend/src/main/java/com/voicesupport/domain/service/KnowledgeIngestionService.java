package com.voicesupport.domain.service;

import com.voicesupport.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.domain.port.out.VectorStorePort;

import java.util.ArrayList;
import java.util.List;

public class KnowledgeIngestionService implements IngestKnowledgeUseCase {

    private final VectorStorePort vectorStorePort;
    private final int chunkSize;
    private final int chunkOverlap;

    public KnowledgeIngestionService(VectorStorePort vectorStorePort, int chunkSize, int chunkOverlap) {
        this.vectorStorePort = vectorStorePort;
        this.chunkSize = chunkSize;
        this.chunkOverlap = chunkOverlap;
    }

    @Override
    public int ingest(String content, String sourceName) {
        return ingest(content, sourceName, null);
    }

    public int ingest(String content, String sourceName, String domain) {
        List<String> chunks = splitIntoChunks(content);
        String currentSection = "default";

        for (int i = 0; i < chunks.size(); i++) {
            String chunk = chunks.get(i);
            String section = extractSection(chunk, currentSection);
            currentSection = section;
            vectorStorePort.store(chunk, sourceName, section, i, domain);
        }

        return chunks.size();
    }

    private List<String> splitIntoChunks(String content) {
        List<String> chunks = new ArrayList<>();
        String[] paragraphs = content.split("\n\n+");
        StringBuilder currentChunk = new StringBuilder();

        for (String paragraph : paragraphs) {
            if (currentChunk.length() + paragraph.length() > chunkSize && !currentChunk.isEmpty()) {
                chunks.add(currentChunk.toString().trim());
                int overlapStart = Math.max(0, currentChunk.length() - chunkOverlap);
                currentChunk = new StringBuilder(currentChunk.substring(overlapStart));
            }
            currentChunk.append(paragraph).append("\n\n");
        }

        if (!currentChunk.isEmpty()) {
            chunks.add(currentChunk.toString().trim());
        }

        return chunks;
    }

    private String extractSection(String chunk, String fallback) {
        for (String line : chunk.split("\n")) {
            if (line.startsWith("# ") || line.startsWith("## ")) {
                return line.replaceFirst("^#+\\s*", "").trim();
            }
        }
        return fallback;
    }
}
