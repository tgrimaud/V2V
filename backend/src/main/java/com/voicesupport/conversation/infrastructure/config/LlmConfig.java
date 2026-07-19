package com.voicesupport.conversation.infrastructure.config;

import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.infrastructure.adapter.out.llm.MistralAnswerAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.llm.OllamaAnswerAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.mistralai.MistralAiChatModel;
import org.springframework.ai.mistralai.MistralAiChatOptions;
import org.springframework.ai.mistralai.api.MistralAiApi;
import org.springframework.ai.ollama.OllamaChatModel;
import org.springframework.ai.ollama.api.OllamaApi;
import org.springframework.ai.ollama.api.OllamaOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// Provider-selectable LLM wording wiring (DEC-011). The chat model is built manually here
// (Mistral/Ollama chat auto-configurations are excluded on the main class) so the provider is
// chosen by voice-support.llm.provider with no domain change. Embeddings stay on Ollama.
@Configuration
public class LlmConfig {

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "mistral-api", matchIfMissing = true)
    public MistralAiChatModel mistralChatModel(
            @Value("${spring.ai.mistralai.api-key:}") String apiKey,
            @Value("${spring.ai.mistralai.chat.options.model:mistral-small-latest}") String model,
            @Value("${spring.ai.mistralai.chat.options.temperature:0.3}") double temperature) {
        MistralAiApi mistralApi = new MistralAiApi(apiKey);
        return MistralAiChatModel.builder()
                .mistralAiApi(mistralApi)
                .defaultOptions(MistralAiChatOptions.builder()
                        .model(model)
                        .temperature(temperature)
                        .build())
                .build();
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "ollama")
    @ConditionalOnMissingBean(OllamaApi.class)
    public OllamaApi llmOllamaApi(@Value("${spring.ai.ollama.base-url:http://localhost:11434}") String baseUrl) {
        return OllamaApi.builder().baseUrl(baseUrl).build();
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "ollama")
    public OllamaChatModel ollamaChatModel(
            OllamaApi ollamaApi,
            @Value("${spring.ai.ollama.chat.model:llama3.1:8b}") String model,
            @Value("${spring.ai.ollama.chat.options.temperature:0.3}") double temperature) {
        return OllamaChatModel.builder()
                .ollamaApi(ollamaApi)
                .defaultOptions(OllamaOptions.builder()
                        .model(model)
                        .temperature(temperature)
                        .build())
                .build();
    }

    @Bean
    public ChatClient answerChatClient(ChatModel chatModel) {
        return ChatClient.builder(chatModel).build();
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "mistral-api", matchIfMissing = true)
    public AnswerGeneratorPort mistralAnswerGenerator(ChatClient answerChatClient, BackendTelemetry telemetry) {
        return new MistralAnswerAdapter(answerChatClient, telemetry);
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "ollama")
    public AnswerGeneratorPort ollamaAnswerGenerator(ChatClient answerChatClient, BackendTelemetry telemetry) {
        return new OllamaAnswerAdapter(answerChatClient, telemetry);
    }
}
