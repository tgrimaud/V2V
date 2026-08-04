package com.voicesupport.conversation.infrastructure.adapter.out.memory;

import java.time.Duration;
import java.util.List;

// Narrow technical seam over the Redis list operations RedisConversationMemoryAdapter needs.
// Kept as an interface so the memory adapter is unit-testable with a manual fake (no live Redis,
// no Mockito); the production implementation (RedisConversationTurnStoreAdapter) wraps
// StringRedisTemplate.
public interface ConversationTurnStore {

    List<String> range(String key);

    void appendTrimExpire(String key, String value, int maxItems, Duration ttl);
}
