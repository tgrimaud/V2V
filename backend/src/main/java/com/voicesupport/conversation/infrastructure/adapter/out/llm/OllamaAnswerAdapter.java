package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.ai.chat.client.ChatClient;

// Ollama wording adapter, the local/offline alternative provider (DEC-011). Same grounded,
// DEC-002-safe contract as the Mistral adapter; only the provider wiring differs.
public class OllamaAnswerAdapter extends AbstractChatClientAnswerAdapter {

    private static final String PROVIDER = "ollama";

    // System prompt is the shared DEC-002 voice prompt in the base class (TASK-BE-053).

    public OllamaAnswerAdapter(
            ChatClient chatClient, BackendTelemetry telemetry, long timeoutMs,
            long streamTimeoutMs, int maxAnswerSentences) {
        super(chatClient, telemetry, timeoutMs, streamTimeoutMs, maxAnswerSentences);
    }

    @Override
    protected String providerName() {
        return PROVIDER;
    }
}
