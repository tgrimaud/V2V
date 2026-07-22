package com.voicesupport.knowledge.infrastructure.config;

import com.voicesupport.knowledge.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import com.voicesupport.knowledge.domain.port.in.SyncKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.out.DomainClassifierPort;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceConnector;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceStatePort;
import com.voicesupport.knowledge.domain.port.out.SyncObserverPort;
import com.voicesupport.knowledge.domain.port.out.VectorSearchPort;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;
import com.voicesupport.knowledge.domain.service.KnowledgeIngestionService;
import com.voicesupport.knowledge.domain.service.KnowledgeRetrievalService;
import com.voicesupport.knowledge.domain.service.KnowledgeSyncService;
import com.voicesupport.knowledge.domain.service.TextChunker;
import com.voicesupport.knowledge.infrastructure.adapter.out.classifier.EmbeddingDomainClassifierAdapter;
import com.voicesupport.knowledge.infrastructure.adapter.out.csv.CsvArticleConnector;
import com.voicesupport.knowledge.infrastructure.adapter.out.markdown.MarkdownFolderConnector;
import com.voicesupport.knowledge.infrastructure.adapter.out.persistence.JpaKnowledgeSourceStateAdapter;
import com.voicesupport.knowledge.infrastructure.adapter.out.persistence.KbSourceStateRepository;
import com.voicesupport.knowledge.infrastructure.adapter.out.vectorstore.PgVectorStoreAdapter;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;
import java.util.Map;

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

    // ADR-0030: anchor texts are short domain descriptors compared (cosine) to each article's
    // embedding at ingestion. They are English because the CSV corpus (Eir) is English.
    @Bean
    public DomainClassifierPort domainClassifier(
            EmbeddingModel embeddingModel,
            @Value("${voice-support.knowledge.classifier.threshold:0.5}") double threshold,
            @Value("${voice-support.knowledge.classifier.max-chars:2000}") int maxChars) {
        Map<String, String> anchors = Map.of(
                "billing", "Billing, invoices, charges, payments, refunds, direct debit, bill amount, "
                        + "overcharge, plan price, credit, account balance and payment methods.",
                "support", "Technical support and troubleshooting: broadband, wifi, router, connection, "
                        + "outage, no service, activation, SIM, device setup, speed and network problems.",
                "commercial", "Sales, offers, plans, upgrades, new subscriptions, contract renewal, "
                        + "bundles, promotions, pricing options and moving home.");
        return new EmbeddingDomainClassifierAdapter(embeddingModel, anchors, threshold, maxChars);
    }

    @Bean
    public CsvArticleConnector csvArticleConnector(
            @Value("${voice-support.knowledge.csv-path:../articles.csv}") String csvPath,
            @Value("${voice-support.knowledge.csv-language:en}") String csvLanguage,
            DomainClassifierPort domainClassifier) {
        return new CsvArticleConnector(csvPath, csvLanguage, domainClassifier);
    }

    // TASK-BE-017: dev-only French copy of the CSV corpus, ingested as a distinct
    // source_type ("csv-article-fr", language fr) so FR questions retrieve FR content
    // without touching the English csv-article source. Missing file → connector yields
    // no documents (logged), so this is a no-op until articles-fr.csv is generated.
    @Bean
    public CsvArticleConnector csvArticleFrConnector(
            @Value("${voice-support.knowledge.csv-fr-path:../articles-fr.csv}") String csvFrPath,
            @Value("${voice-support.knowledge.csv-fr-language:fr}") String csvFrLanguage,
            @Value("${voice-support.knowledge.csv-fr-source-type:csv-article-fr}") String csvFrSourceType,
            DomainClassifierPort domainClassifier) {
        return new CsvArticleConnector(csvFrPath, csvFrLanguage, csvFrSourceType, domainClassifier);
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
            TextChunker textChunker,
            SyncObserverPort syncObserverPort) {
        return new KnowledgeSyncService(
                connectors, knowledgeSourceStatePort, vectorStorePort, textChunker, syncObserverPort);
    }
}
