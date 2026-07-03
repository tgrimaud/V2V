package com.voicesupport.domain.service;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class TextChunkerTest {

    private final TextChunker chunker = new TextChunker(200, 30);

    @Test
    void chunk_splits_content_into_non_empty_chunks() {
        // GIVEN
        String content = "## Section 1\n\nParagraphe un.\n\n## Section 2\n\nParagraphe deux assez long pour tester.";

        // WHEN
        List<TextChunker.Chunk> chunks = chunker.chunk(content);

        // THEN
        assertFalse(chunks.isEmpty());
    }

    @Test
    void chunk_extracts_section_heading_for_chunk() {
        // GIVEN
        String content = "## Problemes Wi-Fi\n\nLe Wi-Fi ne fonctionne pas, verifiez les branchements.";

        // WHEN
        List<TextChunker.Chunk> chunks = chunker.chunk(content);

        // THEN
        assertEquals("Problemes Wi-Fi", chunks.get(0).section());
    }

    @Test
    void chunk_falls_back_to_default_section_when_no_heading() {
        // GIVEN
        String content = "Juste un paragraphe sans titre.";

        // WHEN
        List<TextChunker.Chunk> chunks = chunker.chunk(content);

        // THEN
        assertEquals("default", chunks.get(0).section());
    }
}
