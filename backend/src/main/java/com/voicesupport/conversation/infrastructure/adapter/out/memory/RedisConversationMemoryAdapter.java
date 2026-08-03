package com.voicesupport.conversation.infrastructure.adapter.out.memory;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import com.voicesupport.conversation.domain.port.out.ConversationMemoryPort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

// Redis-backed shared conversation memory (TASK-BE-021, ADR-0008): lets the backend instances
// behind the pilot VIP share short conversation history instead of keeping it process-local
// (InMemoryConversationMemoryAdapter), so consecutive turns of one conversation keep context even
// when the load balancer routes them to different instances. Each conversation is a bounded Redis
// list with a sliding idle TTL; turns are JSON-encoded. Selected by
// voice-support.conversation.memory.store=redis. A Redis outage degrades to empty history rather
// than failing the turn (the answer engine still works, just without shared memory).
public class RedisConversationMemoryAdapter implements ConversationMemoryPort {

    private static final Logger log = LoggerFactory.getLogger(RedisConversationMemoryAdapter.class);
    private static final String KEY_PREFIX = "conversation:memory:";

    private final ConversationTurnStore store;
    private final ObjectMapper objectMapper;
    private final int maxTurns;
    private final Duration ttl;

    public RedisConversationMemoryAdapter(ConversationTurnStore store, ObjectMapper objectMapper,
                                          int maxTurns, Duration ttl) {
        this.store = store;
        this.objectMapper = objectMapper;
        this.maxTurns = Math.max(1, maxTurns);
        this.ttl = ttl;
    }

    @Override
    public List<ConversationTurn> recentTurns(String conversationId) {
        if (isBlank(conversationId)) {
            return List.of();
        }
        try {
            List<ConversationTurn> turns = new ArrayList<>();
            for (String value : store.range(key(conversationId))) {
                turns.add(deserialize(value));
            }
            return List.copyOf(turns);
        } catch (DataAccessException e) {
            log.warn("[CONVERSATION-MEMORY] redis read failed for conversation {} — degrading to empty history",
                    conversationId, e);
            return List.of();
        }
    }

    @Override
    public void append(String conversationId, ConversationTurn turn) {
        if (isBlank(conversationId) || turn == null) {
            return;
        }
        try {
            store.appendTrimExpire(key(conversationId), serialize(turn), maxTurns, ttl);
        } catch (DataAccessException e) {
            log.warn("[CONVERSATION-MEMORY] redis write failed for conversation {} — turn not persisted",
                    conversationId, e);
        }
    }

    private String key(String conversationId) {
        return KEY_PREFIX + conversationId;
    }

    private String serialize(ConversationTurn turn) {
        try {
            return objectMapper.writeValueAsString(turn);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("cannot serialize conversation turn", e);
        }
    }

    private ConversationTurn deserialize(String value) {
        try {
            return objectMapper.readValue(value, ConversationTurn.class);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("cannot deserialize conversation turn", e);
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
