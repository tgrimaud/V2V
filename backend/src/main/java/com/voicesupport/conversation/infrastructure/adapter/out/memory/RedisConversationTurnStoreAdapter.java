package com.voicesupport.conversation.infrastructure.adapter.out.memory;

import org.springframework.data.redis.core.StringRedisTemplate;

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

    @Override
    public void appendTrimExpire(String key, String value, int maxItems, Duration ttl) {
        redis.opsForList().rightPush(key, value);
        redis.opsForList().trim(key, -maxItems, -1);
        redis.expire(key, ttl);
    }
}
