package com.voicesupport.knowledge.domain.service;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TextChunkerTest {

    @Test
    void shouldReturnSingleChunkWhenContentFitsInChunkSize() {
        // GIVEN a chunker larger than the content
        TextChunker chunker = new TextChunker(500, 50);

        // WHEN chunking a short document
        List<TextChunker.Chunk> chunks = chunker.chunk("# Title\n\nShort body.");

        // THEN a single chunk is produced
        assertEquals(1, chunks.size());
    }

    @Test
    void shouldHardSplitASingleParagraphLongerThanChunkSize() {
        // GIVEN a chunk size of 100 and one paragraph (no blank lines) far longer than that
        // (reproduces the TASK-BE-017 embedder failure: a flattened article body as one paragraph)
        TextChunker chunker = new TextChunker(100, 10);
        String oneLongParagraph = "x".repeat(1000);

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk(oneLongParagraph);

        // THEN it is split into several chunks and none exceeds the chunk size (+ overlap margin)
        assertTrue(chunks.size() > 1);
        for (TextChunker.Chunk chunk : chunks) {
            assertTrue(chunk.content().length() <= 110,
                    "chunk length " + chunk.content().length() + " must not blow the embedder limit");
        }
    }

    @Test
    void shouldSplitLongContentIntoMultipleChunks() {
        // GIVEN a small chunk size
        TextChunker chunker = new TextChunker(40, 5);
        String content = "Para one is here.\n\nPara two is here.\n\nPara three is here.";

        // WHEN chunking a document longer than the chunk size
        List<TextChunker.Chunk> chunks = chunker.chunk(content);

        // THEN more than one chunk is produced
        assertTrue(chunks.size() > 1);
    }

    @Test
    void shouldExtractSectionFromMarkdownHeading() {
        // GIVEN content with a level-2 heading
        TextChunker chunker = new TextChunker(500, 50);

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk("## Billing\n\nHow to read your invoice.");

        // THEN the section reflects the heading
        assertEquals("Billing", chunks.get(0).section());
    }

    @Test
    void shouldFallBackToDefaultSectionWhenNoHeading() {
        // GIVEN content without any heading
        TextChunker chunker = new TextChunker(500, 50);

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk("Just a plain paragraph.");

        // THEN the fallback section is used
        assertEquals("default", chunks.get(0).section());
        assertFalse(chunks.isEmpty());
    }
}
