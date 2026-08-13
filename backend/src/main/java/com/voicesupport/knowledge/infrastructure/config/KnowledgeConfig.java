package com.voicesupport.knowledge.infrastructure.config;

import com.voicesupport.knowledge.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import com.voicesupport.knowledge.domain.port.in.SyncKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.out.AudienceClassifierPort;
import com.voicesupport.knowledge.domain.port.out.DomainClassifierPort;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceConnector;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceStatePort;
import com.voicesupport.knowledge.domain.port.out.RetrievalObserverPort;
import com.voicesupport.knowledge.domain.port.out.SyncObserverPort;
import com.voicesupport.knowledge.domain.port.out.VectorSearchPort;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;
import com.voicesupport.knowledge.domain.service.KnowledgeIngestionService;
import com.voicesupport.knowledge.domain.service.KnowledgeRetrievalService;
import com.voicesupport.knowledge.domain.service.KnowledgeSyncService;
import com.voicesupport.knowledge.domain.service.MmrReranker;
import com.voicesupport.knowledge.domain.service.QueryNormalizer;
import com.voicesupport.knowledge.domain.service.TextChunker;
import com.voicesupport.knowledge.infrastructure.adapter.out.classifier.EmbeddingDomainClassifierAdapter;
import com.voicesupport.knowledge.infrastructure.adapter.out.classifier.KeywordAudienceClassifierAdapter;
import com.voicesupport.knowledge.infrastructure.adapter.out.csv.CsvArticleConnector;
import com.voicesupport.knowledge.infrastructure.adapter.out.markdown.MarkdownFolderConnector;
import com.voicesupport.knowledge.infrastructure.adapter.out.persistence.JpaKnowledgeSourceStateAdapter;
import com.voicesupport.knowledge.infrastructure.adapter.out.persistence.KbSourceStateRepository;
import com.voicesupport.knowledge.infrastructure.adapter.out.vectorstore.PgVectorStoreAdapter;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.ollama.OllamaEmbeddingModel;
import org.springframework.ai.ollama.api.OllamaApi;
import org.springframework.ai.ollama.api.OllamaOptions;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

@Configuration
public class KnowledgeConfig {

    // Explicit Ollama embedding model (TASK-BE-025). The Ollama embedding auto-configuration builds
    // an OllamaApi on a default RestClient with no read/connect timeout, so a slow/hung Ollama would
    // stall every similaritySearch (embedding runs before the pgvector query) on Spring's defaults
    // before GlobalExceptionHandler maps to 503. Defining the EmbeddingModel here (auto-config backs
    // off via @ConditionalOnMissingBean) lets us bound the embedding HTTP call like the LLM client
    // (env-driven). Stays Ollama nomic-embed-text (768d) — embeddings are never Mistral (1024d).
    @Bean
    public EmbeddingModel embeddingModel(
            @Value("${spring.ai.ollama.base-url:http://localhost:11434}") String baseUrl,
            @Value("${spring.ai.ollama.embedding.model:nomic-embed-text}") String model,
            @Value("${voice-support.embedding.timeout-ms:5000}") long timeoutMs,
            @Value("${voice-support.embedding.connect-timeout-ms:3000}") long connectMs) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout((int) connectMs);
        factory.setReadTimeout((int) timeoutMs);
        OllamaApi ollamaApi = OllamaApi.builder().baseUrl(baseUrl)
                .restClientBuilder(RestClient.builder().requestFactory(factory)).build();
        return OllamaEmbeddingModel.builder()
                .ollamaApi(ollamaApi)
                .defaultOptions(OllamaOptions.builder().model(model).build())
                .build();
    }

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

    // ADR-0034: deterministic, high-precision audience boundary for the mixed operator corpus.
    // The default markers cover the observed BUG-005 agent-desk content (back office, R6/ION,
    // VAA/VRD, vérification d'aptitude); extend the list to widen the internal partition without
    // a rebuild. Precision over recall: only unambiguous markers tag an article internal.
    @Bean
    public AudienceClassifierPort audienceClassifier(
            @Value("${voice-support.knowledge.audience.internal-markers:"
                    + "back office,vérification d'aptitude,r6/ion,vaa,vrd}") List<String> internalMarkers) {
        return new KeywordAudienceClassifierAdapter(internalMarkers);
    }

    @Bean
    public CsvArticleConnector csvArticleConnector(
            @Value("${voice-support.knowledge.csv-path:../articles.csv}") String csvPath,
            @Value("${voice-support.knowledge.csv-language:en}") String csvLanguage,
            DomainClassifierPort domainClassifier,
            AudienceClassifierPort audienceClassifier) {
        return new CsvArticleConnector(csvPath, csvLanguage, domainClassifier, audienceClassifier);
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
            DomainClassifierPort domainClassifier,
            AudienceClassifierPort audienceClassifier) {
        return new CsvArticleConnector(
                csvFrPath, csvFrLanguage, csvFrSourceType, domainClassifier, audienceClassifier);
    }

    @Bean
    public IngestKnowledgeUseCase ingestKnowledgeUseCase(VectorStorePort vectorStorePort, TextChunker textChunker) {
        return new KnowledgeIngestionService(vectorStorePort, textChunker);
    }

    // TASK-BE-028: MMR diversity re-ranking over the over-fetched dense candidates (BUG-003).
    // Over-fetch top-k * fetch-multiplier, then greedily re-select top-k balancing relevance
    // (dense score) against lexical redundancy. Disabled by default: the TASK-BE-027 live A/B
    // (reports/ab-mmr-2026-08-13.md) showed lambda=0.7 degrades recall@8/stability (compressed
    // nomic scores → redundancy dominates) and lambda=0.9 is only neutral, so MMR is kept as a
    // tested, env-toggleable dedup guard rather than an on-by-default lever. If enabling, use
    // lambda>=0.9.
    //
    // TASK-BE-029: query greeting-normalization strips a leading greeting from the embedding query
    // (raw question still drives guardrail/LLM/logs). Disabled by default: the TASK-BE-027 A/B
    // (reports/ab-query-norm-2026-08-13.md) showed it is strictly neutral (the sup-fr-slow eviction
    // persists after stripping "Bonjour," → the miss is core-phrasing, not the greeting). Kept as a
    // tested, env-toggleable robustness guard. Independent, orthogonal toggle to MMR.
    @Bean
    public KnowledgeRetrievalUseCase knowledgeRetrievalUseCase(
            VectorSearchPort vectorSearchPort,
            RetrievalObserverPort retrievalObserver,
            @Value("${voice-support.knowledge.retrieval.mmr.enabled:false}") boolean mmrEnabled,
            @Value("${voice-support.knowledge.retrieval.mmr.lambda:0.9}") double mmrLambda,
            @Value("${voice-support.knowledge.retrieval.mmr.fetch-multiplier:3}") int fetchMultiplier,
            @Value("${voice-support.knowledge.retrieval.query-normalization.enabled:false}")
            boolean queryNormalizationEnabled) {
        MmrReranker reranker = mmrEnabled ? new MmrReranker(mmrLambda) : null;
        QueryNormalizer normalizer = queryNormalizationEnabled ? new QueryNormalizer() : null;
        if (reranker == null && normalizer == null) {
            return new KnowledgeRetrievalService(vectorSearchPort);
        }
        return new KnowledgeRetrievalService(
                vectorSearchPort, reranker, retrievalObserver, fetchMultiplier, normalizer);
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
