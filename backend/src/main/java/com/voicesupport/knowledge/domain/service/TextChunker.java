package com.voicesupport.knowledge.domain.service;

import java.util.ArrayList;
import java.util.List;

public class TextChunker {

    private final int chunkSize;
    private final int chunkOverlap;

    public TextChunker(int chunkSize, int chunkOverlap) {
        this.chunkSize = chunkSize;
        this.chunkOverlap = chunkOverlap;
    }

    public List<Chunk> chunk(String content) {
        List<Chunk> chunks = new ArrayList<>();
        String section = "default";
        for (String text : splitIntoChunks(content)) {
            section = extractSection(text, section);
            chunks.add(new Chunk(text, section));
        }
        return chunks;
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

    public record Chunk(String content, String section) {
    }
}
