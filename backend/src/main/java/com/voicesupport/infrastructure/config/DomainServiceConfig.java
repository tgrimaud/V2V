package com.voicesupport.infrastructure.config;

import com.voicesupport.domain.port.in.AskQuestionUseCase;
import com.voicesupport.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import com.voicesupport.domain.port.out.VectorSearchPort;
import com.voicesupport.domain.port.out.VectorStorePort;
import com.voicesupport.domain.service.ConversationService;
import com.voicesupport.domain.service.EscalationDetector;
import com.voicesupport.domain.service.GuardrailService;
import com.voicesupport.domain.service.KnowledgeIngestionService;
import com.voicesupport.domain.service.QueryReformulator;
import com.voicesupport.domain.service.StreamingConversationService;
import com.voicesupport.infrastructure.adapter.out.llm.MistralLlmAdapter;
import com.voicesupport.infrastructure.adapter.out.llm.OllamaLlmAdapter;
import com.voicesupport.infrastructure.adapter.out.persistence.InMemoryConversationEventStore;
import com.voicesupport.infrastructure.adapter.out.vectorstore.PgVectorStoreAdapter;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.mistralai.MistralAiChatModel;
import org.springframework.ai.mistralai.MistralAiChatOptions;
import org.springframework.ai.mistralai.api.MistralAiApi;
import org.springframework.ai.ollama.OllamaChatModel;
import org.springframework.ai.ollama.api.OllamaApi;
import org.springframework.ai.ollama.api.OllamaOptions;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DomainServiceConfig {

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "mistral-api", matchIfMissing = true)
    public MistralAiChatModel mistralChatModel(
            @Value("${spring.ai.mistralai.api-key}") String apiKey,
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
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "ollama", matchIfMissing = false)
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
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "ollama", matchIfMissing = false)
    public OllamaApi ollamaApi(@Value("${spring.ai.ollama.base-url:http://localhost:11434}") String baseUrl) {
        return OllamaApi.builder().baseUrl(baseUrl).build();
    }

    @Bean
    public ChatClient chatClient(ChatModel chatModel) {
        return ChatClient.builder(chatModel).build();
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "mistral-api", matchIfMissing = true)
    public MistralLlmAdapter mistralLlmAdapter(ChatClient chatClient) {
        return new MistralLlmAdapter(chatClient);
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "ollama", matchIfMissing = false)
    public OllamaLlmAdapter ollamaLlmAdapter(ChatClient chatClient) {
        return new OllamaLlmAdapter(chatClient);
    }

    @Bean
    public PgVectorStoreAdapter pgVectorStoreAdapter(VectorStore vectorStore) {
        return new PgVectorStoreAdapter(vectorStore);
    }

    @Bean
    public VectorStorePort vectorStorePort(PgVectorStoreAdapter adapter) {
        return adapter;
    }

    @Bean
    public VectorSearchPort vectorSearchPort(PgVectorStoreAdapter adapter) {
        return adapter;
    }

    @Bean
    public EscalationDetector escalationDetector() {
        return new EscalationDetector();
    }

    @Bean
    public GuardrailService guardrailService(
            @Value("${voice-support.guardrails.confidence-threshold:0.65}") double confidenceThreshold) {
        return new GuardrailService(confidenceThreshold);
    }

    @Bean
    public QueryReformulator queryReformulator() {
        return new QueryReformulator();
    }

    @Bean
    public ConversationEventStore conversationEventStore() {
        return new InMemoryConversationEventStore();
    }

    @Bean
    public AskQuestionUseCase askQuestionUseCase(VectorSearchPort vectorSearchPort, LlmPort llmPort,
                                                  EscalationDetector escalationDetector,
                                                  GuardrailService guardrailService,
                                                  QueryReformulator queryReformulator,
                                                  ConversationEventStore eventStore) {
        return new ConversationService(vectorSearchPort, llmPort, escalationDetector,
                guardrailService, queryReformulator, eventStore);
    }

    @Bean
    public StreamingConversationService streamingConversationService(
            VectorSearchPort vectorSearchPort, LlmStreamingPort llmStreamingPort,
            EscalationDetector escalationDetector, GuardrailService guardrailService,
            QueryReformulator queryReformulator,
            ConversationEventStore eventStore) {
        return new StreamingConversationService(vectorSearchPort, llmStreamingPort,
                escalationDetector, guardrailService, queryReformulator, eventStore);
    }

    @Bean
    public IngestKnowledgeUseCase ingestKnowledgeUseCase(
            VectorStorePort vectorStorePort,
            @Value("${voice-support.knowledge.chunk-size:500}") int chunkSize,
            @Value("${voice-support.knowledge.chunk-overlap:50}") int chunkOverlap) {
        return new KnowledgeIngestionService(vectorStorePort, chunkSize, chunkOverlap);
    }
}
