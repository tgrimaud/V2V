package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.ai.chat.client.ChatClient;

// OpenAI wording adapter (gpt-5), a third selectable LLM chat provider for benchmarking against
// Mistral (DEC-011, TASK-BE-049). Same grounded, DEC-002-safe contract as the other adapters;
// only the provider wiring differs. Embeddings stay on Ollama; STT/TTS stay on the voice runtime.
public class OpenAiAnswerAdapter extends AbstractChatClientAnswerAdapter {

    private static final String PROVIDER = "openai";

    // System prompt is the shared DEC-002 voice prompt in the base class (TASK-BE-053).

    public OpenAiAnswerAdapter(
            ChatClient chatClient, BackendTelemetry telemetry, long timeoutMs,
            long streamTimeoutMs, int maxAnswerSentences) {
        super(chatClient, telemetry, timeoutMs, streamTimeoutMs, maxAnswerSentences);
    }

    @Override
    protected String providerName() {
        return PROVIDER;
    }
}
