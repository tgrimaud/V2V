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

    @Test
    void shouldNotDuplicateTheOverlapRegionInsideAChunk() {
        // GIVEN a long single paragraph (flattened article body) longer than the chunk size (BUG-003:
        // the old double overlap re-stated the same words inside one chunk, e.g. "... cela\n\n cela ...")
        TextChunker chunker = new TextChunker(120, 30);
        String body = "Une consommation anormale peut venir d un appareil connecte "
                + "ou d une residence secondaire mais cela peut aussi indiquer un probleme "
                + "de facturation qu il faut verifier ligne par ligne sur la facture detaillee.";

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk(body);

        // THEN no chunk restates the same 4-word window twice inside itself
        assertTrue(chunks.size() > 1);
        for (TextChunker.Chunk chunk : chunks) {
            assertFalse(hasRepeatedWindow(chunk.content()),
                    "chunk duplicates a window internally: [" + chunk.content() + "]");
        }
    }

    @Test
    void shouldNotEmitAChunkThatContainsOnlyHeadings() {
        // GIVEN nested headings followed by a body long enough to force a flush (BUG-003 header-only chunk)
        TextChunker chunker = new TextChunker(80, 10);
        String content = "# Base de connaissance\n\n## Connexion Internet\n\n### Ma box ne se connecte plus\n\n"
                + "Verifiez le branchement des cables puis redemarrez la box et patientez deux minutes "
                + "avant de relancer un test de connexion complet depuis un ordinateur filaire.";

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk(content);

        // THEN every chunk carries real body text, not only markdown headings
        for (TextChunker.Chunk chunk : chunks) {
            assertTrue(hasBodyLine(chunk.content()),
                    "header-only chunk produced: [" + chunk.content() + "]");
        }
    }

    @Test
    void shouldNotCutWordsInTheMiddleWhenHardSplitting() {
        // GIVEN a long paragraph of real words far longer than the chunk size
        TextChunker chunker = new TextChunker(60, 10);
        String body = "alpha bravo charlie delta echo foxtrot golf hotel india juliett kilo "
                + "lima mike november oscar papa quebec romeo sierra tango uniform victor whiskey";
        List<String> vocabulary = List.of(body.split(" "));

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk(body);

        // THEN every whitespace-separated token of every chunk is a real, whole word
        assertTrue(chunks.size() > 1);
        for (TextChunker.Chunk chunk : chunks) {
            for (String token : chunk.content().split("\\s+")) {
                if (!token.isEmpty()) {
                    assertTrue(vocabulary.contains(token), "mid-word cut produced token: [" + token + "]");
                }
            }
        }
    }

    @Test
    void shouldExtractSectionFromLevelThreeHeading() {
        // GIVEN a level-3 heading (### was ignored by the old extractSection)
        TextChunker chunker = new TextChunker(500, 50);

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk("### Ma box ne se connecte plus\n\nRedemarrez la box.");

        // THEN the section reflects the level-3 heading
        assertEquals("Ma box ne se connecte plus", chunks.get(0).section());
    }

    // --- Deterministic boundary/overlap tests (TASK-QA-018): exact-content assertions that pin
    // the chunk-size flush edge, the hard-split edge, and the word-boundary overlap tail so a
    // subtle `<`/`<=`/negate mutation in the chunking algorithm is caught, not silently shipped. ---

    @Test
    void flushBoundary_bufferPlusPieceExactlyAtChunkSizeDoesNotFlush() {
        // GIVEN two 5-char paragraphs and a chunk size of exactly their combined length (10)
        TextChunker chunker = new TextChunker(10, 0);

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk("aaaaa\n\nbbbbb");

        // THEN they stay in one chunk — pins `sum > chunkSize` (a `>=` mutant would flush at ==)
        assertEquals(1, chunks.size());
        assertEquals("aaaaa\n\nbbbbb", chunks.get(0).content());
    }

    @Test
    void hardSplitBoundary_paragraphExactlyAtChunkSizeIsNotSplit() {
        // GIVEN a single paragraph whose length is exactly the chunk size (10)
        TextChunker chunker = new TextChunker(10, 2);

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk("0123456789");

        // THEN it is kept whole — pins `length <= chunkSize` (a `<` mutant would hard-split it)
        assertEquals(1, chunks.size());
        assertEquals("0123456789", chunks.get(0).content());
    }

    @Test
    void overlapTail_carriesTheWordBoundarySuffixIntoTheNextChunk() {
        // GIVEN a flush where the 6-char tail starts with a space (" cd ef")
        TextChunker chunker = new TextChunker(10, 6);

        // WHEN a second paragraph forces a flush
        List<TextChunker.Chunk> chunks = chunker.chunk("ab cd ef\n\ngh ij");

        // THEN chunk 2 begins with the snapped-forward overlap "cd ef" — pins the overlap guard
        // (negate → "") and the `substring(i+1)` word-snap (empty-return mutant → "")
        assertEquals(2, chunks.size());
        assertEquals("ab cd ef", chunks.get(0).content());
        assertEquals("cd ef\n\ngh ij", chunks.get(1).content());
    }

    @Test
    void overlapTail_withNoWhitespaceReturnsTheWholeTail() {
        // GIVEN a flush where the 4-char tail has no whitespace ("efgh")
        TextChunker chunker = new TextChunker(10, 4);

        // WHEN a second paragraph forces a flush
        List<TextChunker.Chunk> chunks = chunker.chunk("abcdefgh\n\nij kl");

        // THEN the whole tail carries over — pins the final `return tail` (empty-return mutant → "")
        assertEquals(2, chunks.size());
        assertEquals("abcdefgh", chunks.get(0).content());
        assertEquals("efgh\n\nij kl", chunks.get(1).content());
    }

    @Test
    void overlapTail_snapsForwardPastAMidTailWhitespaceDroppingThePartialWord() {
        // GIVEN a flush where the 7-char tail is "ab cdef" (whitespace in the middle, not leading)
        TextChunker chunker = new TextChunker(10, 7);

        // WHEN a second paragraph forces a flush
        List<TextChunker.Chunk> chunks = chunker.chunk("xxab cdef\n\nGH");

        // THEN the partial leading word "ab" is dropped, "cdef" carries over — pins the snap loop
        // (a skip-the-loop mutant would keep "ab cdef", observable after strip)
        assertEquals(2, chunks.size());
        assertEquals("xxab cdef", chunks.get(0).content());
        assertEquals("cdef\n\nGH", chunks.get(1).content());
    }

    @Test
    void overlapTail_bufferExactlyAtOverlapLengthProducesNoOverlap() {
        // GIVEN a flushed body chunk whose length equals the overlap exactly (5)
        TextChunker chunker = new TextChunker(5, 5);

        // WHEN a second paragraph forces a flush
        List<TextChunker.Chunk> chunks = chunker.chunk("abcde\n\nfg");

        // THEN no overlap is carried (buffer not longer than overlap) — pins `length <= chunkOverlap`
        // (a `<` mutant would re-emit the whole buffer as overlap)
        assertEquals(2, chunks.size());
        assertEquals("abcde", chunks.get(0).content());
        assertEquals("fg", chunks.get(1).content());
    }

    @Test
    void addRemaining_headingOnlyDocumentStillProducesTheHeadingChunk() {
        // GIVEN a document that is only a heading (no body text at all)
        TextChunker chunker = new TextChunker(500, 50);

        // WHEN chunking
        List<TextChunker.Chunk> chunks = chunker.chunk("# Title only");

        // THEN the heading is still emitted because it is the sole content — pins the
        // `chunks.isEmpty()` fallback branch (a heading-only doc must not vanish)
        assertEquals(1, chunks.size());
        assertEquals("# Title only", chunks.get(0).content());
        assertEquals("Title only", chunks.get(0).section());
    }

    private static boolean hasBodyLine(String content) {
        for (String line : content.split("\n")) {
            String stripped = line.strip();
            if (!stripped.isEmpty() && !stripped.matches("^#{1,6}\\s.*")) {
                return true;
            }
        }
        return false;
    }

    private static boolean hasRepeatedWindow(String content) {
        String[] words = content.replace("\n", " ").split("\\s+");
        for (int i = 0; i + 7 < words.length; i++) {
            String first = words[i] + " " + words[i + 1] + " " + words[i + 2] + " " + words[i + 3];
            for (int j = i + 4; j + 3 < words.length; j++) {
                String next = words[j] + " " + words[j + 1] + " " + words[j + 2] + " " + words[j + 3];
                if (first.equals(next)) {
                    return true;
                }
            }
        }
        return false;
    }
}
