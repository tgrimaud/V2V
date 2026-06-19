package com.voicesupport.infrastructure.config;

import com.voicesupport.domain.port.in.AskQuestionUseCase;
import com.voicesupport.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.VectorSearchPort;
import com.voicesupport.domain.port.out.VectorStorePort;
import com.voicesupport.domain.service.ConversationService;
import com.voicesupport.domain.service.EscalationDetector;
import com.voicesupport.domain.service.KnowledgeIngestionService;
import com.voicesupport.infrastructure.adapter.out.llm.MistralLlmAdapter;
import com.voicesupport.infrastructure.adapter.out.llm.OllamaLlmAdapter;
import com.voicesupport.infrastructure.adapter.out.persistence.InMemoryConversationEventStore;
import com.voicesupport.infrastructure.adapter.out.vectorstore.PgVectorStoreAdapter;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.mistralai.MistralAiChatModel;
import org.springframework.ai.mistralai.MistralAiChatOptions;
import org.springframework.ai.mistralai.api.MistralAiApi;
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
    public ChatClient chatClient(ChatModel chatModel) {
        return ChatClient.builder(chatModel).build();
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "mistral-api", matchIfMissing = true)
    public LlmPort mistralLlmPort(ChatClient chatClient) {
        return new MistralLlmAdapter(chatClient);
    }

    @Bean
    @ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "ollama", matchIfMissing = false)
    public LlmPort ollamaLlmPort(ChatClient chatClient) {
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
    public ConversationEventStore conversationEventStore() {
        return new InMemoryConversationEventStore();
    }

    @Bean
    public AskQuestionUseCase askQuestionUseCase(VectorSearchPort vectorSearchPort, LlmPort llmPort,
                                                  EscalationDetector escalationDetector,
                                                  ConversationEventStore eventStore) {
        return new ConversationService(vectorSearchPort, llmPort, escalationDetector, eventStore);
    }

    @Bean
    public IngestKnowledgeUseCase ingestKnowledgeUseCase(
            VectorStorePort vectorStorePort,
            @Value("${voice-support.knowledge.chunk-size:500}") int chunkSize,
            @Value("${voice-support.knowledge.chunk-overlap:50}") int chunkOverlap) {
        return new KnowledgeIngestionService(vectorStorePort, chunkSize, chunkOverlap);
    }
}
