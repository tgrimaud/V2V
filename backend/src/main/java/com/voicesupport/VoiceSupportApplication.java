package com.voicesupport;

import org.springframework.ai.model.mistralai.autoconfigure.MistralAiChatAutoConfiguration;
import org.springframework.ai.model.mistralai.autoconfigure.MistralAiEmbeddingAutoConfiguration;
import org.springframework.ai.model.mistralai.autoconfigure.MistralAiModerationAutoConfiguration;
import org.springframework.ai.model.ollama.autoconfigure.OllamaChatAutoConfiguration;
import org.springframework.ai.model.openai.autoconfigure.OpenAiAudioSpeechAutoConfiguration;
import org.springframework.ai.model.openai.autoconfigure.OpenAiAudioTranscriptionAutoConfiguration;
import org.springframework.ai.model.openai.autoconfigure.OpenAiChatAutoConfiguration;
import org.springframework.ai.model.openai.autoconfigure.OpenAiEmbeddingAutoConfiguration;
import org.springframework.ai.model.openai.autoconfigure.OpenAiImageAutoConfiguration;
import org.springframework.ai.model.openai.autoconfigure.OpenAiModerationAutoConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

import java.security.Security;

// Ollama is used for embeddings only (nomic-embed-text, 768d) feeding the pgvector store;
// its chat auto-configuration is excluded. Mistral is the LLM chat provider, but its chat
// model is built manually in the conversation LlmConfig (provider selectable via
// voice-support.llm.provider), so the Mistral chat/embedding/moderation auto-configurations
// are excluded — embeddings must stay on Ollama (768d), never Mistral (1024d). The OpenAI
// starter (TASK-BE-033 benchmark candidate) follows the same rule: its chat model is built
// manually in LlmConfig. ALL of its auto-configurations are excluded — not only chat/embedding/
// moderation but also audio-speech/audio-transcription/image, because those instantiate eagerly
// and hard-require spring.ai.openai.api-key, so they crash startup whenever OPENAI_API_KEY is
// unset (i.e. every non-OpenAI run). The manual chat bean is gated on provider=openai instead.
@SpringBootApplication(exclude = {
        OllamaChatAutoConfiguration.class,
        MistralAiChatAutoConfiguration.class,
        MistralAiEmbeddingAutoConfiguration.class,
        MistralAiModerationAutoConfiguration.class,
        OpenAiChatAutoConfiguration.class,
        OpenAiEmbeddingAutoConfiguration.class,
        OpenAiModerationAutoConfiguration.class,
        OpenAiAudioSpeechAutoConfiguration.class,
        OpenAiAudioTranscriptionAutoConfiguration.class,
        OpenAiImageAutoConfiguration.class
})
public class VoiceSupportApplication {

    public static void main(String[] args) {
        hardenDnsCaching();
        SpringApplication.run(VoiceSupportApplication.class, args);
    }

    // BUG-014: do not cache negative DNS results for the JVM lifetime. During container/network
    // churn a transient UnknownHostException (e.g. "ollama") would otherwise be cached and every
    // subsequent embedding call would keep failing until a restart. With a 0 negative TTL the
    // bounded retry on the embedding client re-resolves and self-heals within the same turn.
    static void hardenDnsCaching() {
        Security.setProperty("networkaddress.cache.negative.ttl", "0");
    }
}
