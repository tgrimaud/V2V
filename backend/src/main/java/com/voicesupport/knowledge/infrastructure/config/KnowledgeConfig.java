package com.voicesupport.knowledge.infrastructure.config;

import com.voicesupport.knowledge.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import com.voicesupport.knowledge.domain.port.in.SyncKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceConnector;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceStatePort;
import com.voicesupport.knowledge.domain.port.out.VectorSearchPort;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;
import com.voicesupport.knowledge.domain.service.KnowledgeIngestionService;
import com.voicesupport.knowledge.domain.service.KnowledgeRetrievalService;
import com.voicesupport.knowledge.domain.service.KnowledgeSyncService;
import com.voicesupport.knowledge.domain.service.TextChunker;
import com.voicesupport.knowledge.infrastructure.adapter.out.markdown.MarkdownFolderConnector;
import com.voicesupport.knowledge.infrastructure.adapter.out.persistence.JpaKnowledgeSourceStateAdapter;
import com.voicesupport.knowledge.infrastructure.adapter.out.persistence.KbSourceStateRepository;
import com.voicesupport.knowledge.infrastructure.adapter.out.vectorstore.PgVectorStoreAdapter;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
public class KnowledgeConfig {

    // Single adapter instance exposed as both the write port (VectorStorePort) and the
    // read port (VectorSearchPort); Spring injects it by interface type where required.
    @Bean
    public PgVectorStoreAdapter pgVectorStoreAdapter(VectorStore vectorStore) {
        return new PgVectorStoreAdapter(vectorStore);
    }

    @Bean
    public KnowledgeSourceStatePort knowledgeSourceStatePort(KbSourceStateRepository repository) {
        return new JpaKnowledgeSourceStateAdapter(repository);
    }

    @Bean
    public TextChunker textChunker(
            @Value("${voice-support.knowledge.chunk-size:500}") int chunkSize,
            @Value("${voice-support.knowledge.chunk-overlap:50}") int chunkOverlap) {
        return new TextChunker(chunkSize, chunkOverlap);
    }

    @Bean
    public MarkdownFolderConnector markdownFolderConnector(
            @Value("${voice-support.knowledge.markdown-path:../knowledge-base}") String markdownPath,
            @Value("${voice-support.knowledge.default-language:fr}") String defaultLanguage) {
        return new MarkdownFolderConnector(markdownPath, defaultLanguage);
    }

    @Bean
    public IngestKnowledgeUseCase ingestKnowledgeUseCase(VectorStorePort vectorStorePort, TextChunker textChunker) {
        return new KnowledgeIngestionService(vectorStorePort, textChunker);
    }

    @Bean
    public KnowledgeRetrievalUseCase knowledgeRetrievalUseCase(VectorSearchPort vectorSearchPort) {
        return new KnowledgeRetrievalService(vectorSearchPort);
    }

    @Bean
    public SyncKnowledgeUseCase syncKnowledgeUseCase(
            List<KnowledgeSourceConnector> connectors,
            KnowledgeSourceStatePort knowledgeSourceStatePort,
            VectorStorePort vectorStorePort,
            TextChunker textChunker) {
        return new KnowledgeSyncService(connectors, knowledgeSourceStatePort, vectorStorePort, textChunker);
    }
}
