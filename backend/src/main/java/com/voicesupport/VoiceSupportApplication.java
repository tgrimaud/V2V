package com.voicesupport;

import org.springframework.ai.model.mistralai.autoconfigure.MistralAiChatAutoConfiguration;
import org.springframework.ai.model.mistralai.autoconfigure.MistralAiEmbeddingAutoConfiguration;
import org.springframework.ai.model.mistralai.autoconfigure.MistralAiModerationAutoConfiguration;
import org.springframework.ai.model.ollama.autoconfigure.OllamaChatAutoConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

// Ollama is used for embeddings only (nomic-embed-text, 768d) feeding the pgvector store;
// its chat auto-configuration is excluded. Mistral is the LLM chat provider, but its chat
// model is built manually in the conversation LlmConfig (provider selectable via
// voice-support.llm.provider), so the Mistral chat/embedding/moderation auto-configurations
// are excluded — embeddings must stay on Ollama (768d), never Mistral (1024d).
@SpringBootApplication(exclude = {
        OllamaChatAutoConfiguration.class,
        MistralAiChatAutoConfiguration.class,
        MistralAiEmbeddingAutoConfiguration.class,
        MistralAiModerationAutoConfiguration.class
})
public class VoiceSupportApplication {

    public static void main(String[] args) {
        SpringApplication.run(VoiceSupportApplication.class, args);
    }
}
