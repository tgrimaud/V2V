package com.voicesupport;

import org.springframework.ai.model.ollama.autoconfigure.OllamaChatAutoConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

// Ollama is used for embeddings only (nomic-embed-text, 768d) feeding the pgvector store.
// The chat auto-configuration is excluded: chat/LLM wiring lands with the answer engine.
@SpringBootApplication(exclude = {OllamaChatAutoConfiguration.class})
public class VoiceSupportApplication {

    public static void main(String[] args) {
        SpringApplication.run(VoiceSupportApplication.class, args);
    }
}
