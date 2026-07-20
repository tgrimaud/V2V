package com.voicesupport.conversation.domain.service;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("SentenceSegmenter (streamed token -> complete sentences)")
class SentenceSegmenterTest {

    private final SentenceSegmenter segmenter = new SentenceSegmenter();

    @Test
    @DisplayName("emits a sentence only once a terminator is followed by whitespace")
    void emitsOnBoundary() {
        // GIVEN a terminator arrives at the end of a token (no following char yet)
        assertTrue(segmenter.feed("Bonjour.").isEmpty());

        // WHEN the next token brings the following whitespace
        List<String> sentences = segmenter.feed(" Voici");

        // THEN the completed sentence is emitted and the remainder stays buffered
        assertEquals(List.of("Bonjour."), sentences);
        assertEquals(List.of("Voici"), segmenter.flush());
    }

    @Test
    @DisplayName("never splits a decimal amount before the terminator that ends the sentence")
    void doesNotSplitDecimalAmount() {
        // WHEN a sentence containing a decimal amount is fed with a trailing boundary
        List<String> sentences = segmenter.feed("Cela coûte 5.99 euros. ");

        // THEN the decimal point is not a boundary; only the sentence-final '.' splits
        assertEquals(List.of("Cela coûte 5.99 euros."), sentences);
    }

    @Test
    @DisplayName("splits multiple sentences present in a single token and keeps the tail buffered")
    void splitsMultipleSentences() {
        // WHEN two full sentences plus a partial one arrive together
        List<String> sentences = segmenter.feed("Un. Deux! Trois");

        // THEN both complete sentences are emitted, the partial one waits for flush
        assertEquals(List.of("Un.", "Deux!"), sentences);
        assertEquals(List.of("Trois"), segmenter.flush());
    }

    @Test
    @DisplayName("treats a newline as a sentence boundary")
    void newlineIsBoundary() {
        // WHEN a token ends a line
        List<String> sentences = segmenter.feed("Première ligne\nseconde");

        // THEN the first line is a complete chunk
        assertEquals(List.of("Première ligne"), sentences);
    }

    @Test
    @DisplayName("flush returns the remaining buffer and empties it")
    void flushReturnsRemainder() {
        // GIVEN buffered content with no trailing boundary
        segmenter.feed("Sans ponctuation finale");

        // WHEN flushing
        List<String> remainder = segmenter.flush();

        // THEN the remainder is returned once and the buffer is empty afterwards
        assertEquals(List.of("Sans ponctuation finale"), remainder);
        assertTrue(segmenter.flush().isEmpty());
    }
}
