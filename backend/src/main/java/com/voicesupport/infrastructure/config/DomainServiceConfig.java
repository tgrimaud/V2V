package com.voicesupport.infrastructure.config;

import com.voicesupport.domain.model.AgentProfile;
import com.voicesupport.domain.model.AgentRegistry;
import com.voicesupport.domain.port.in.AdminDashboardUseCase;
import com.voicesupport.domain.port.in.AskQuestionStreamingUseCase;
import com.voicesupport.domain.port.in.AskQuestionUseCase;
import com.voicesupport.domain.port.in.CompareInvoicesUseCase;
import com.voicesupport.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.domain.port.in.SyncKnowledgeSourceUseCase;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.ConversationStore;
import com.voicesupport.domain.port.out.KnowledgeSourceConnector;
import com.voicesupport.domain.port.out.KnowledgeSourceStatePort;
import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import com.voicesupport.domain.port.out.VectorSearchPort;
import com.voicesupport.domain.port.out.VectorStorePort;
import com.voicesupport.domain.service.AdminDashboardService;
import com.voicesupport.domain.service.ConversationOrchestrator;
import com.voicesupport.domain.service.EscalationDetector;
import com.voicesupport.domain.service.GuardrailService;
import com.voicesupport.domain.service.InvoiceComparisonService;
import com.voicesupport.domain.service.IntentClassifier;
import com.voicesupport.domain.service.KnowledgeIngestionService;
import com.voicesupport.domain.service.KnowledgeSyncService;
import com.voicesupport.domain.service.QueryReformulator;
import com.voicesupport.domain.service.TextChunker;
import com.voicesupport.infrastructure.adapter.out.persistence.InMemoryConversationEventStore;
import com.voicesupport.infrastructure.adapter.out.persistence.InMemoryConversationStore;
import com.voicesupport.infrastructure.adapter.out.persistence.JpaKnowledgeSourceStateAdapter;
import com.voicesupport.infrastructure.adapter.out.persistence.KbSourceStateRepository;
import com.voicesupport.infrastructure.adapter.out.source.MarkdownFolderConnector;
import com.voicesupport.infrastructure.adapter.out.vectorstore.PgVectorStoreAdapter;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
public class DomainServiceConfig {

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
    public ConversationStore conversationStore() {
        return new InMemoryConversationStore();
    }

    @Bean
    public AdminDashboardUseCase adminDashboardUseCase(ConversationEventStore eventStore) {
        return new AdminDashboardService(eventStore);
    }

    @Bean
    public AgentRegistry agentRegistry() {
        return new AgentRegistry(
                List.of(AgentProfile.support(), AgentProfile.billing(), AgentProfile.commercial()),
                "support"
        );
    }

    @Bean
    public IntentClassifier intentClassifier(AgentRegistry agentRegistry) {
        return new IntentClassifier(agentRegistry);
    }

    @Bean
    public ConversationOrchestrator conversationOrchestrator(
            VectorSearchPort vectorSearchPort, LlmPort llmPort, LlmStreamingPort llmStreamingPort,
            EscalationDetector escalationDetector, GuardrailService guardrailService,
            QueryReformulator queryReformulator, IntentClassifier intentClassifier,
            ConversationEventStore eventStore, ConversationStore conversationStore) {
        return new ConversationOrchestrator(vectorSearchPort, llmPort, llmStreamingPort,
                escalationDetector, guardrailService, queryReformulator, intentClassifier,
                eventStore, conversationStore);
    }

    @Bean
    public AskQuestionUseCase askQuestionUseCase(ConversationOrchestrator orchestrator) {
        return orchestrator;
    }

    @Bean
    public AskQuestionStreamingUseCase askQuestionStreamingUseCase(ConversationOrchestrator orchestrator) {
        return orchestrator;
    }

    @Bean
    public CompareInvoicesUseCase compareInvoicesUseCase() {
        return new InvoiceComparisonService();
    }

    @Bean
    public TextChunker textChunker(
            @Value("${voice-support.knowledge.chunk-size:500}") int chunkSize,
            @Value("${voice-support.knowledge.chunk-overlap:50}") int chunkOverlap) {
        return new TextChunker(chunkSize, chunkOverlap);
    }

    @Bean
    public IngestKnowledgeUseCase ingestKnowledgeUseCase(VectorStorePort vectorStorePort, TextChunker textChunker) {
        return new KnowledgeIngestionService(vectorStorePort, textChunker);
    }

    @Bean
    public KnowledgeSourceStatePort knowledgeSourceStatePort(KbSourceStateRepository repository) {
        return new JpaKnowledgeSourceStateAdapter(repository);
    }

    @Bean
    public MarkdownFolderConnector markdownFolderConnector(
            @Value("${voice-support.knowledge.markdown-path:../knowledge-base}") String markdownPath,
            @Value("${voice-support.knowledge.default-language:fr}") String defaultLanguage) {
        return new MarkdownFolderConnector(markdownPath, defaultLanguage);
    }

    @Bean
    public SyncKnowledgeSourceUseCase syncKnowledgeSourceUseCase(
            List<KnowledgeSourceConnector> connectors,
            KnowledgeSourceStatePort knowledgeSourceStatePort,
            VectorStorePort vectorStorePort,
            TextChunker textChunker) {
        return new KnowledgeSyncService(connectors, knowledgeSourceStatePort, vectorStorePort, textChunker);
    }
}
