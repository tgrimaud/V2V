package com.voicesupport;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(exclude = {
    org.springframework.ai.model.mistralai.autoconfigure.MistralAiEmbeddingAutoConfiguration.class,
    org.springframework.ai.model.mistralai.autoconfigure.MistralAiChatAutoConfiguration.class,
    org.springframework.ai.model.mistralai.autoconfigure.MistralAiModerationAutoConfiguration.class,
    org.springframework.ai.model.ollama.autoconfigure.OllamaChatAutoConfiguration.class
})
public class VoiceSupportApplication {

    public static void main(String[] args) {
        SpringApplication.run(VoiceSupportApplication.class, args);
    }
}
