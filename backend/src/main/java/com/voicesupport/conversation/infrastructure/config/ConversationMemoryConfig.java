package com.voicesupport.conversation.infrastructure.config;

import com.voicesupport.conversation.domain.port.out.ConversationMemoryPort;
import com.voicesupport.conversation.domain.port.out.DeliveryDeduplicationPort;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.conversation.infrastructure.adapter.out.idempotency.InMemoryDeliveryDeduplicationAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.ConversationTurnStore;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.InMemoryConversationMemoryAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.RedisConversationMemoryAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.RedisConversationTurnStoreAdapter;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;

// Conversation persistence + delivery de-duplication wiring (TASK-BE-021/037, ADR-0008/0009).
// Extracted from ConversationConfig to stay within the 200-line budget; bean definitions and
// behaviour are unchanged.
@Configuration
public class ConversationMemoryConfig {

    private static final Logger log = LoggerFactory.getLogger(ConversationMemoryConfig.class);

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

    // Normalized channel envelope de-duplication (TASK-BE-037, ADR-0009): a process-local bounded
    // LRU of recently-seen idempotency keys so an at-least-once channel (e.g. the Genesys Audio
    // Connector) that re-delivers the same inbound event is not answered twice. Only deliveries
    // carrying an idempotency signal are de-duplicated, so the current web path is unaffected. A
    // shared store (Redis/DB) can replace this behind DeliveryDeduplicationPort for multi-node.
    @Bean
    public DeliveryDeduplicationPort deliveryDeduplicationPort(
            @Value("${voice-support.conversation.idempotency.max-keys:100000}") int maxKeys) {
        return new InMemoryDeliveryDeduplicationAdapter(maxKeys);
    }

    @Bean
    public IdempotentDeliveryGuard idempotentDeliveryGuard(DeliveryDeduplicationPort deliveryDeduplicationPort) {
        return new IdempotentDeliveryGuard(deliveryDeduplicationPort);
    }
}
