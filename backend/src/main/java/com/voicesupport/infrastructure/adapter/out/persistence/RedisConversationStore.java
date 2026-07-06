package com.voicesupport.infrastructure.adapter.out.persistence;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.Conversation;
import com.voicesupport.domain.port.out.ConversationStore;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

public class RedisConversationStore implements ConversationStore {

    private static final String KEY_PREFIX = "conversation:";

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final Duration ttl;

    public RedisConversationStore(StringRedisTemplate redisTemplate, ObjectMapper objectMapper, Duration ttl) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.ttl = ttl;
    }

    @Override
    public Conversation load(String conversationId) {
        String json = redisTemplate.opsForValue().get(key(conversationId));
        return json == null ? new Conversation(conversationId) : readSnapshot(json);
    }

    @Override
    public void save(String conversationId, Conversation conversation) {
        redisTemplate.opsForValue().set(key(conversationId), writeSnapshot(conversation), ttl);
    }

    private Conversation readSnapshot(String json) {
        try {
            ConversationSnapshot snapshot = objectMapper.readValue(json, ConversationSnapshot.class);
            return snapshot.toDomain();
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Cannot read Redis conversation snapshot", e);
        }
    }

    private String writeSnapshot(Conversation conversation) {
        try {
            return objectMapper.writeValueAsString(ConversationSnapshot.fromDomain(conversation));
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Cannot write Redis conversation snapshot", e);
        }
    }

    private String key(String conversationId) {
        return KEY_PREFIX + conversationId;
    }

    private record ConversationSnapshot(String id, List<StoredTurn> turns, Instant startedAt,
                                        String sessionLanguage, String currentAgentId) {

        static ConversationSnapshot fromDomain(Conversation conversation) {
            List<StoredTurn> turns = conversation.getTurns().stream().map(StoredTurn::fromDomain).toList();
            return new ConversationSnapshot(conversation.getId(), turns, conversation.getStartedAt(),
                    conversation.getSessionLanguage(), conversation.getCurrentAgentId());
        }

        Conversation toDomain() {
            List<Conversation.Turn> domainTurns = turns.stream().map(StoredTurn::toDomain).toList();
            return new Conversation(id, domainTurns, startedAt, sessionLanguage, currentAgentId);
        }
    }

    private record StoredTurn(Conversation.Role role, String text, Instant timestamp, List<Citation> citations) {

        static StoredTurn fromDomain(Conversation.Turn turn) {
            return new StoredTurn(turn.role(), turn.text(), turn.timestamp(), turn.citations());
        }

        Conversation.Turn toDomain() {
            return new Conversation.Turn(role, text, timestamp, citations);
        }
    }
}
