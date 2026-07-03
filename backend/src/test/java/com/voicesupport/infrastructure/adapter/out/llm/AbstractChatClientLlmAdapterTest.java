package com.voicesupport.infrastructure.adapter.out.llm;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AbstractChatClientLlmAdapterTest {

    private final TestAdapter adapter = new TestAdapter();

    @Test
    void build_system_message_injects_context_into_default_prompt() {
        // GIVEN
        List<String> chunks = List.of("chunk-A", "chunk-B");

        // WHEN
        String message = adapter.systemMessage(chunks, List.of(), null);

        // THEN
        assertTrue(message.contains("chunk-A\n---\nchunk-B"));
        assertFalse(message.contains("{context}"));
    }

    @Test
    void build_system_message_uses_override_prompt_when_provided() {
        // GIVEN
        String override = "Custom prompt with {context} placeholder.";

        // WHEN
        String message = adapter.systemMessage(List.of("data"), List.of(), override);

        // THEN
        assertTrue(message.startsWith("Custom prompt with data placeholder."));
    }

    @Test
    void build_system_message_appends_history_only_when_present() {
        // GIVEN
        List<String> history = List.of("USER: hi", "ASSISTANT: hello");

        // WHEN
        String withHistory = adapter.systemMessage(List.of("ctx"), history, null);
        String withoutHistory = adapter.systemMessage(List.of("ctx"), List.of(), null);

        // THEN
        assertTrue(withHistory.contains("USER: hi\nASSISTANT: hello"));
        assertFalse(withoutHistory.contains("Historique de la conversation"));
    }

    private static class TestAdapter extends AbstractChatClientLlmAdapter {
        TestAdapter() {
            super(null);
        }

        String systemMessage(List<String> chunks, List<String> history, String systemPrompt) {
            return buildSystemMessage(chunks, history, systemPrompt);
        }

        @Override
        protected String defaultSystemPrompt() {
            return "Default prompt.\nContexte:\n{context}";
        }
    }
}
