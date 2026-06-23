package com.voicesupport.domain.service;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class TextChunkerTest {

    private final TextChunker chunker = new TextChunker(200, 30);

    @Test
    void shouldSplitContentIntoChunks() {
        String content = "## Section 1\n\nParagraphe un.\n\n## Section 2\n\nParagraphe deux assez long pour tester.";

        List<TextChunker.Chunk> chunks = chunker.chunk(content);

        assertFalse(chunks.isEmpty());
    }

    @Test
    void shouldExtractSectionHeadingForChunk() {
        String content = "## Problemes Wi-Fi\n\nLe Wi-Fi ne fonctionne pas, verifiez les branchements.";

        List<TextChunker.Chunk> chunks = chunker.chunk(content);

        assertEquals("Problemes Wi-Fi", chunks.get(0).section());
    }

    @Test
    void shouldFallBackToDefaultSectionWhenNoHeading() {
        String content = "Juste un paragraphe sans titre.";

        List<TextChunker.Chunk> chunks = chunker.chunk(content);

        assertEquals("default", chunks.get(0).section());
    }
}
