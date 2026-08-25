package com.voicesupport.conversation.infrastructure.config;

import com.voicesupport.conversation.application.service.AnswerService;
import com.voicesupport.conversation.application.service.ConversationService;
import com.voicesupport.conversation.application.service.RetrievalGroundingService;
import com.voicesupport.conversation.application.service.StreamingConversationService;
import com.voicesupport.conversation.application.service.WarmUpService;
import com.voicesupport.conversation.domain.port.in.AnswerQuestionUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.domain.port.in.WarmUpUseCase;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.ConversationMemoryPort;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.port.out.StreamingAnswerGeneratorPort;
import com.voicesupport.conversation.domain.service.InputGuardrail;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.domain.service.RetrievalConfidenceGuardrail;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.ConversationTurnStore;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.InMemoryConversationMemoryAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.RedisConversationMemoryAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.RedisConversationTurnStoreAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

@Configuration
public class ConversationConfig {

    private static final Logger log = LoggerFactory.getLogger(ConversationConfig.class);

    // ADR-0034: the vague-turn markers (contentless continuers like "vas-y", "ok") that trigger a
    // clarify instead of retrieving a weak, possibly wrong-audience match (BUG-005). Configurable so
    // the list can be tuned per deployment/language without a rebuild.
    @Bean
    public InputGuardrail inputGuardrail(
            @Value("${voice-support.conversation.vague-markers:"
                    + "vas-y,vas y,allez-y,allez y,continue,continuez,poursuis,poursuivez,ensuite,"
                    + "la suite,go,go on,go ahead,ok,okay,d'accord,dac,dacc,alors,donc,bah,ben,euh,"
                    + "hmm,voila,voilà,et}") List<String> vagueMarkers) {
        return new InputGuardrail(vagueMarkers);
    }

    // ADR-0034: three-band confidence policy. Below confidence-threshold -> advisor hand-off; between
    // it and clarify-threshold -> ask to clarify; at/above -> answer. clarify-threshold <= threshold
    // disables the clarify band. Definitive billing proof threshold stays gated by OQ-002.
    @Bean
    public RetrievalConfidenceGuardrail retrievalConfidenceGuardrail(
            @Value("${voice-support.conversation.confidence-threshold:0.5}") double confidenceThreshold,
            @Value("${voice-support.conversation.clarify-threshold:0.62}") double clarifyThreshold) {
        return new RetrievalConfidenceGuardrail(confidenceThreshold, clarifyThreshold);
    }

    @Bean
    public GroundQueryUseCase groundQueryUseCase(
            InputGuardrail inputGuardrail,
            RetrievalConfidenceGuardrail retrievalConfidenceGuardrail,
            KnowledgeRetrievalPort knowledgeRetrievalPort) {
        return new RetrievalGroundingService(inputGuardrail, retrievalConfidenceGuardrail, knowledgeRetrievalPort);
    }

    @Bean
    public OutputGuardrail outputGuardrail() {
        return new OutputGuardrail();
    }

    // Answer-language decision (TASK-BE-015): default language used when a turn is too ambiguous to
    // detect and no session language is established. English for the Eir pilot; configurable per
    // deployment via voice-support.conversation.default-language.
    @Bean
    public LanguageDetector languageDetector(
            @Value("${voice-support.conversation.default-language:en}") String defaultLanguage) {
        return new LanguageDetector(AnswerLanguage.fromCode(defaultLanguage));
    }

    @Bean
    public AnswerQuestionUseCase answerQuestionUseCase(
            GroundQueryUseCase groundQueryUseCase,
            AnswerGeneratorPort answerGeneratorPort,
            OutputGuardrail outputGuardrail,
            LanguageDetector languageDetector,
            BackendTelemetry backendTelemetry) {
        return new AnswerService(
                groundQueryUseCase, answerGeneratorPort, outputGuardrail, languageDetector, backendTelemetry);
    }

    // Conversation memory backend (TASK-BE-021, ADR-0008). Default `memory` = process-local
    // (single-node dev/tests); `redis` = shared across the backend instances behind the pilot VIP
    // so a conversation keeps context when turns land on different instances. StringRedisTemplate is
    // resolved lazily (ObjectProvider) so `memory` mode never requires a Redis bean. Selected via
    // CONVERSATION_STORE.
    @Bean
    public ConversationMemoryPort conversationMemoryPort(
            @Value("${voice-support.conversation.memory.store:memory}") String store,
            @Value("${voice-support.conversation.memory.max-turns:6}") int maxTurns,
            @Value("${voice-support.conversation.memory.max-conversations:10000}") int maxConversations,
            @Value("${voice-support.conversation.memory.ttl-seconds:3600}") long ttlSeconds,
            ObjectProvider<StringRedisTemplate> redisTemplateProvider,
            ObjectMapper objectMapper) {
        if ("redis".equalsIgnoreCase(store)) {
            log.info("[CONVERSATION-MEMORY] store=redis max-turns={} ttl-seconds={} — shared across backend instances",
                    maxTurns, ttlSeconds);
            ConversationTurnStore turnStore =
                    new RedisConversationTurnStoreAdapter(redisTemplateProvider.getObject());
            return new RedisConversationMemoryAdapter(
                    turnStore, objectMapper, maxTurns, Duration.ofSeconds(ttlSeconds));
        }
        log.info("[CONVERSATION-MEMORY] store=memory max-turns={} max-conversations={} — process-local (single node)",
                maxTurns, maxConversations);
        return new InMemoryConversationMemoryAdapter(maxTurns, maxConversations);
    }

    @Bean
    public ConverseUseCase converseUseCase(
            AnswerQuestionUseCase answerQuestionUseCase,
            ConversationMemoryPort conversationMemoryPort,
            @Value("${voice-support.conversation.retrieval.top-k:5}") int topK) {
        return new ConversationService(answerQuestionUseCase, conversationMemoryPort, topK);
    }

    @Bean
    public ConverseStreamUseCase converseStreamUseCase(
            GroundQueryUseCase groundQueryUseCase,
            StreamingAnswerGeneratorPort streamingAnswerGeneratorPort,
            OutputGuardrail outputGuardrail,
            ConversationMemoryPort conversationMemoryPort,
            LanguageDetector languageDetector,
            BackendTelemetry backendTelemetry,
            @Value("${voice-support.conversation.retrieval.top-k:5}") int topK) {
        return new StreamingConversationService(groundQueryUseCase, streamingAnswerGeneratorPort,
                outputGuardrail, conversationMemoryPort, languageDetector, backendTelemetry, topK);
    }

    // Connect-time warm-up of the embedding + LLM (TASK-BE-017 / ADR-0037): the voice runtime calls
    // POST /api/conversation/warm-up on WebRTC connect so the first real turn is warm (lever 2). The
    // warm query is configurable per deployment/language; it touches no conversation memory.
    @Bean
    public WarmUpUseCase warmUpUseCase(
            KnowledgeRetrievalPort knowledgeRetrievalPort,
            AnswerGeneratorPort answerGeneratorPort,
            BackendTelemetry backendTelemetry,
            @Value("${voice-support.conversation.warmup.query:hello}") String warmQuery,
            @Value("${voice-support.conversation.default-language:en}") String defaultLanguage) {
        return new WarmUpService(knowledgeRetrievalPort, answerGeneratorPort, backendTelemetry,
                warmQuery, AnswerLanguage.fromCode(defaultLanguage));
    }

    // Bounded daemon pool for SSE stream workers (TASK-BE-007): each /converse-stream turn holds a
    // worker for the whole stream, so max-threads caps concurrent streams and a bounded queue caps
    // the backlog. Beyond both, submissions are rejected (AbortPolicy) and the controller degrades
    // to a sanitized 503 rather than queueing unboundedly — same fail-fast stance as the LLM pool.
    @Bean(destroyMethod = "shutdown")
    public ExecutorService sseStreamExecutor(
            @Value("${voice-support.conversation.stream.max-threads:16}") int maxThreads,
            @Value("${voice-support.conversation.stream.queue-capacity:32}") int queueCapacity) {
        ThreadFactory factory = runnable -> {
            Thread thread = new Thread(runnable, "sse-stream");
            thread.setDaemon(true);
            return thread;
        };
        return new ThreadPoolExecutor(maxThreads, maxThreads, 60L, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>(queueCapacity), factory, new ThreadPoolExecutor.AbortPolicy());
    }
}
