package com.voicesupport.conversation.domain.service;

import java.util.ArrayList;
import java.util.List;

// Buffers streamed LLM tokens and yields complete sentences (TASK-BE-007). A sentence boundary is
// a terminator (. ! ?) followed by whitespace, or a newline. A '.' preceded by a digit is never a
// boundary, so a decimal amount (e.g. 5.99) is never split before the DEC-002 amount check runs.
// A terminator with no following character yet is kept buffered until the next token arrives, so a
// split is never decided on a partial token; flush() emits whatever remains at stream end.
public class SentenceSegmenter {

    private final StringBuilder buffer = new StringBuilder();

    public List<String> feed(String token) {
        if (token != null && !token.isEmpty()) {
            buffer.append(token);
        }
        return extractComplete();
    }

    public List<String> flush() {
        String rest = buffer.toString().strip();
        buffer.setLength(0);
        return rest.isEmpty() ? List.of() : List.of(rest);
    }

    private List<String> extractComplete() {
        List<String> sentences = new ArrayList<>();
        int start = 0;
        for (int i = 0; i < buffer.length(); i++) {
            if (isBoundary(i)) {
                addSentence(sentences, start, i + 1);
                start = i + 1;
            }
        }
        if (start > 0) {
            buffer.delete(0, start);
        }
        return sentences;
    }

    private void addSentence(List<String> sentences, int from, int to) {
        String sentence = buffer.substring(from, to).strip();
        if (!sentence.isEmpty()) {
            sentences.add(sentence);
        }
    }

    private boolean isBoundary(int index) {
        char current = buffer.charAt(index);
        if (current == '\n') {
            return true;
        }
        if (current != '.' && current != '!' && current != '?') {
            return false;
        }
        if (index + 1 >= buffer.length() || !Character.isWhitespace(buffer.charAt(index + 1))) {
            return false;
        }
        return current != '.' || index == 0 || !Character.isDigit(buffer.charAt(index - 1));
    }
}
