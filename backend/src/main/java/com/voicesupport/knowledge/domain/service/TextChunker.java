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
        StringBuilder currentChunk = new StringBuilder();

        for (String paragraph : content.split("\n\n+")) {
            // A single long paragraph (e.g. HTML-flattened article body, denser in French) must be
            // hard-split so no chunk exceeds chunkSize and blows the embedder token limit.
            for (String piece : hardSplit(paragraph)) {
                if (currentChunk.length() + piece.length() > chunkSize && !currentChunk.isEmpty()) {
                    chunks.add(currentChunk.toString().trim());
                    int overlapStart = Math.max(0, currentChunk.length() - chunkOverlap);
                    currentChunk = new StringBuilder(currentChunk.substring(overlapStart));
                }
                currentChunk.append(piece).append("\n\n");
            }
        }

        if (!currentChunk.isEmpty()) {
            chunks.add(currentChunk.toString().trim());
        }

        return chunks;
    }

    private List<String> hardSplit(String paragraph) {
        if (paragraph.length() <= chunkSize) {
            return List.of(paragraph);
        }
        List<String> pieces = new ArrayList<>();
        int step = Math.max(1, chunkSize - chunkOverlap);
        for (int start = 0; start < paragraph.length(); start += step) {
            pieces.add(paragraph.substring(start, Math.min(paragraph.length(), start + chunkSize)));
        }
        return pieces;
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
