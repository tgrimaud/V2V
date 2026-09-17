package com.voicesupport.conversation.infrastructure.config;

import com.voicesupport.conversation.infrastructure.adapter.out.llm.MistralAnswerAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.llm.OllamaAnswerAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.llm.OpenAiAnswerAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.mistralai.MistralAiChatModel;
import org.springframework.ai.mistralai.MistralAiChatOptions;
import org.springframework.ai.mistralai.api.MistralAiApi;
import org.springframework.ai.ollama.OllamaChatModel;
import org.springframework.ai.ollama.api.OllamaApi;
import org.springframework.ai.ollama.api.OllamaOptions;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.ai.retry.RetryUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import jakarta.annotation.PostConstruct;
import java.util.Set;

// Provider-selectable LLM wording wiring (DEC-011). The chat model is built manually here
// (Mistral/Ollama chat auto-configurations are excluded on the main class) so the provider is
// chosen by voice-support.llm.provider with no domain change. Embeddings stay on Ollama.
@Configuration
public class LlmConfig {

    private static final Set<String> SUPPORTED_PROVIDERS = Set.of("mistral-api", "ollama", "openai");

    @Value("${voice-support.llm.provider:openai}")
    private String provider;

    // Fail fast on a misconfigured provider: without this, an unknown value builds no ChatModel bean
    // and startup dies later with an opaque "no qualifying bean of type ChatModel" on answerChatClient.
    @PostConstruct
    void validateProvider() {
        if (provider == null || !SUPPORTED_PROVIDERS.contains(provider.trim())) {
            throw new IllegalStateException("Unknown voice-support.llm.provider '" + provider
                    + "'. Supported values: mistral-api, ollama, openai.");
        }
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "mistral-api")
    public MistralAiChatModel mistralChatModel(
            @Value("${spring.ai.mistralai.api-key:}") String apiKey,
            @Value("${spring.ai.mistralai.base-url:https://api.mistral.ai}") String baseUrl,
            @Value("${spring.ai.mistralai.chat.options.model:mistral-small-latest}") String model,
            @Value("${spring.ai.mistralai.chat.options.temperature:0.2}") double temperature,
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
            @Value("${spring.ai.ollama.chat.options.temperature:0.2}") double temperature) {
        return OllamaChatModel.builder()
                .ollamaApi(ollamaApi)
                .defaultOptions(OllamaOptions.builder()
                        .model(model)
                        .temperature(temperature)
                        .build())
                .build();
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "openai", matchIfMissing = true)
    public OpenAiChatModel openAiChatModel(
            @Value("${spring.ai.openai.api-key:}") String apiKey,
            @Value("${spring.ai.openai.base-url:https://api.openai.com}") String baseUrl,
            @Value("${spring.ai.openai.chat.options.model:gpt-5}") String model,
            // gpt-5 accepts only the default temperature (1.0); a lower value is rejected with a 400.
            // Kept configurable via OPENAI_CHAT_TEMPERATURE for models that allow tuning it.
            @Value("${spring.ai.openai.chat.options.temperature:1.0}") double temperature,
            // Voice latency lever (TASK-BE-049): gpt-5 is a reasoning model. Without this it spends
            // ~128 reasoning tokens on a trivial turn (~2.6 s); reasoning_effort=minimal drops that to
            // 0 tokens (~0.95 s), which matters for the mouth-to-ear budget. Blank disables it (send
            // nothing) so a non-reasoning model (e.g. gpt-4o) is not rejected with a 400.
            @Value("${spring.ai.openai.chat.options.reasoning-effort:minimal}") String reasoningEffort,
            @Value("${voice-support.llm.timeout-ms:8000}") long timeoutMs,
            @Value("${voice-support.llm.connect-timeout-ms:3000}") long connectMs) {
        // Provider HTTP read timeout closes a stalled socket (TASK-BE-012 medium fix); the executor
        // timeout is only a backstop. Read timeout tracks the logical LLM timeout, same as Mistral.
        OpenAiApi openAiApi = OpenAiApi.builder()
                .baseUrl(baseUrl)
                .apiKey(apiKey)
                .restClientBuilder(timeoutRestClientBuilder(connectMs, timeoutMs))
                .build();
        OpenAiChatOptions.Builder options = OpenAiChatOptions.builder()
                .model(model)
                .temperature(temperature);
        if (reasoningEffort != null && !reasoningEffort.isBlank()) {
            options.reasoningEffort(reasoningEffort.trim());
        }
        return OpenAiChatModel.builder()
                .openAiApi(openAiApi)
                .defaultOptions(options.build())
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
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "mistral-api")
    public MistralAnswerAdapter mistralAnswerGenerator(
            ChatClient answerChatClient, BackendTelemetry telemetry,
            @Value("${voice-support.llm.timeout-ms:8000}") long timeoutMs,
            @Value("${voice-support.llm.stream-timeout-ms:10000}") long streamTimeoutMs,
            @Value("${voice-support.llm.max-answer-sentences:3}") int maxAnswerSentences) {
        return new MistralAnswerAdapter(answerChatClient, telemetry, timeoutMs, streamTimeoutMs, maxAnswerSentences);
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "ollama")
    public OllamaAnswerAdapter ollamaAnswerGenerator(
            ChatClient answerChatClient, BackendTelemetry telemetry,
            @Value("${voice-support.llm.timeout-ms:8000}") long timeoutMs,
            @Value("${voice-support.llm.stream-timeout-ms:10000}") long streamTimeoutMs,
            @Value("${voice-support.llm.max-answer-sentences:3}") int maxAnswerSentences) {
        return new OllamaAnswerAdapter(answerChatClient, telemetry, timeoutMs, streamTimeoutMs, maxAnswerSentences);
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "openai", matchIfMissing = true)
    public OpenAiAnswerAdapter openAiAnswerGenerator(
            ChatClient answerChatClient, BackendTelemetry telemetry,
            @Value("${voice-support.llm.timeout-ms:8000}") long timeoutMs,
            @Value("${voice-support.llm.stream-timeout-ms:10000}") long streamTimeoutMs,
            @Value("${voice-support.llm.max-answer-sentences:3}") int maxAnswerSentences) {
        return new OpenAiAnswerAdapter(answerChatClient, telemetry, timeoutMs, streamTimeoutMs, maxAnswerSentences);
    }

    private static RestClient.Builder timeoutRestClientBuilder(long connectMs, long readMs) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout((int) connectMs);
        factory.setReadTimeout((int) readMs);
        return RestClient.builder().requestFactory(factory);
    }
}
