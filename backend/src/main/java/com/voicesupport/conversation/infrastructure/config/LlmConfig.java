package com.voicesupport.conversation.infrastructure.config;

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
import org.springframework.ai.retry.RetryUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

// Provider-selectable LLM wording wiring (DEC-011). The chat model is built manually here
// (Mistral/Ollama chat auto-configurations are excluded on the main class) so the provider is
// chosen by voice-support.llm.provider with no domain change. Embeddings stay on Ollama.
@Configuration
public class LlmConfig {

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "mistral-api", matchIfMissing = true)
    public MistralAiChatModel mistralChatModel(
            @Value("${spring.ai.mistralai.api-key:}") String apiKey,
            @Value("${spring.ai.mistralai.base-url:https://api.mistral.ai}") String baseUrl,
            @Value("${spring.ai.mistralai.chat.options.model:mistral-small-latest}") String model,
            @Value("${spring.ai.mistralai.chat.options.temperature:0.3}") double temperature,
            @Value("${voice-support.llm.timeout-ms:8000}") long timeoutMs,
            @Value("${voice-support.llm.connect-timeout-ms:3000}") long connectMs) {
        // Provider HTTP read timeout closes a stalled socket (TASK-BE-012 medium fix); the
        // executor timeout is only a backstop. Read timeout tracks the logical LLM timeout.
        MistralAiApi mistralApi = new MistralAiApi(baseUrl, apiKey,
                timeoutRestClientBuilder(connectMs, timeoutMs), RetryUtils.DEFAULT_RESPONSE_ERROR_HANDLER);
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
    public OllamaApi llmOllamaApi(
            @Value("${spring.ai.ollama.base-url:http://localhost:11434}") String baseUrl,
            @Value("${voice-support.llm.timeout-ms:8000}") long timeoutMs,
            @Value("${voice-support.llm.connect-timeout-ms:3000}") long connectMs) {
        return OllamaApi.builder().baseUrl(baseUrl)
                .restClientBuilder(timeoutRestClientBuilder(connectMs, timeoutMs)).build();
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

    // Returns the concrete adapter type so the single instance resolves for both the sync
    // AnswerGeneratorPort and the StreamingAnswerGeneratorPort (TASK-BE-007); both are implemented
    // by AbstractChatClientAnswerAdapter.
    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "mistral-api", matchIfMissing = true)
    public MistralAnswerAdapter mistralAnswerGenerator(
            ChatClient answerChatClient, BackendTelemetry telemetry,
            @Value("${voice-support.llm.timeout-ms:8000}") long timeoutMs) {
        return new MistralAnswerAdapter(answerChatClient, telemetry, timeoutMs);
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "ollama")
    public OllamaAnswerAdapter ollamaAnswerGenerator(
            ChatClient answerChatClient, BackendTelemetry telemetry,
            @Value("${voice-support.llm.timeout-ms:8000}") long timeoutMs) {
        return new OllamaAnswerAdapter(answerChatClient, telemetry, timeoutMs);
    }

    private static RestClient.Builder timeoutRestClientBuilder(long connectMs, long readMs) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout((int) connectMs);
        factory.setReadTimeout((int) readMs);
        return RestClient.builder().requestFactory(factory);
    }
}
