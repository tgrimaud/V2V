package com.voicesupport.conversation.infrastructure.adapter.out.memory;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

// Redis list-backed store: one list per conversation key. Append uses RPUSH + LTRIM (keep only
// the last maxItems entries) + EXPIRE (sliding idle TTL); read uses LRANGE. Redis list ops keep
// the append atomic and avoid a read-modify-write of the whole history under concurrent turns.
public class RedisConversationTurnStoreAdapter implements ConversationTurnStore {

    private final StringRedisTemplate redis;

    public RedisConversationTurnStoreAdapter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public List<String> range(String key) {
        List<String> values = redis.opsForList().range(key, 0, -1);
        return values == null ? List.of() : values;
    }

    // Pipeline RPUSH -> LTRIM -> PEXPIRE in a single round-trip instead of three sequential
    // calls, so the hot turn path pays one network round-trip to Redis rather than three
    // (TASK-BE-024). Command order inside the pipeline is preserved, so the list is still
    // bounded to the last maxItems entries and the sliding idle TTL is refreshed on every
    // append, exactly as before. StringRedisTemplate uses UTF-8 string serializers, so
    // encoding key/value as UTF-8 bytes here matches the opsForList() serialization; PEXPIRE
    // (millis) preserves the full Duration precision that opsForList().expire(ttl) used.
    @Override
    public void appendTrimExpire(String key, String value, int maxItems, Duration ttl) {
        byte[] rawKey = key.getBytes(StandardCharsets.UTF_8);
        byte[] rawValue = value.getBytes(StandardCharsets.UTF_8);
        long ttlMillis = ttl.toMillis();
        redis.executePipelined((RedisCallback<Object>) connection -> {
            connection.listCommands().rPush(rawKey, rawValue);
            connection.listCommands().lTrim(rawKey, -maxItems, -1);
            connection.keyCommands().pExpire(rawKey, ttlMillis);
            return null;
        });
    }
}
