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
        StringBuilder buffer = new StringBuilder();
        String section = "default";
        for (String paragraph : content.split("\n\n+")) {
            String trimmed = paragraph.strip();
            if (trimmed.isEmpty()) {
                continue;
            }
            section = latestHeading(trimmed, section);
            for (String piece : hardSplit(trimmed)) {
                if (shouldFlush(buffer, piece)) {
                    chunks.add(new Chunk(buffer.toString().strip(), section));
                    buffer = new StringBuilder(overlapTail(buffer.toString()));
                }
                appendPiece(buffer, piece);
            }
        }
        addRemaining(chunks, buffer, section);
        return chunks;
    }

    // Flush only when the buffer would overflow AND already carries body text, so accumulated
    // heading-only paragraphs are never emitted alone: they stay attached to the following body.
    private boolean shouldFlush(StringBuilder buffer, String piece) {
        return buffer.length() + piece.length() > chunkSize && hasBodyText(buffer.toString());
    }

    private void appendPiece(StringBuilder buffer, String piece) {
        if (buffer.length() > 0) {
            buffer.append("\n\n");
        }
        buffer.append(piece);
    }

    private void addRemaining(List<Chunk> chunks, StringBuilder buffer, String section) {
        String text = buffer.toString().strip();
        if (!text.isEmpty() && (hasBodyText(text) || chunks.isEmpty())) {
            chunks.add(new Chunk(text, section));
        }
    }

    // Contiguous (non-overlapping) hard split of an over-long paragraph, cut on word boundaries.
    // Contiguous is deliberate: the single cross-chunk overlap is added once at flush time, so the
    // previous double-overlap (hardSplit step + flush overlap) that duplicated text inside a chunk
    // no longer happens.
    private List<String> hardSplit(String paragraph) {
        if (paragraph.length() <= chunkSize) {
            return List.of(paragraph);
        }
        int maxPiece = Math.max(1, chunkSize - chunkOverlap);
        List<String> pieces = new ArrayList<>();
        int start = 0;
        while (start < paragraph.length()) {
            int end = snapBackToBoundary(paragraph, start, Math.min(paragraph.length(), start + maxPiece));
            pieces.add(paragraph.substring(start, end).strip());
            start = end;
        }
        return pieces;
    }

    private int snapBackToBoundary(String text, int start, int end) {
        if (end >= text.length()) {
            return end;
        }
        int i = end;
        while (i > start && !Character.isWhitespace(text.charAt(i))) {
            i--;
        }
        return i > start ? i : end;
    }

    // Word-boundary overlap tail: never re-emit a whole small chunk (that caused duplication) and
    // never start mid-word (snap forward past the first whitespace).
    private String overlapTail(String buffer) {
        if (chunkOverlap <= 0 || buffer.length() <= chunkOverlap) {
            return "";
        }
        String tail = buffer.substring(buffer.length() - chunkOverlap);
        for (int i = 0; i < tail.length(); i++) {
            if (Character.isWhitespace(tail.charAt(i))) {
                return tail.substring(i + 1);
            }
        }
        return tail;
    }

    private String latestHeading(String paragraph, String fallback) {
        String section = fallback;
        for (String line : paragraph.split("\n")) {
            String stripped = line.strip();
            if (isHeadingLine(stripped)) {
                section = stripped.replaceFirst("^#{1,6}\\s*", "").strip();
            }
        }
        return section;
    }

    private boolean hasBodyText(String text) {
        for (String line : text.split("\n")) {
            String stripped = line.strip();
            if (!stripped.isEmpty() && !isHeadingLine(stripped)) {
                return true;
            }
        }
        return false;
    }

    private boolean isHeadingLine(String line) {
        return line.matches("^#{1,6}\\s.*");
    }

    public record Chunk(String content, String section) {
    }
}
