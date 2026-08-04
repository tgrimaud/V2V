package com.voicesupport.conversation.infrastructure.adapter.out.memory;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("RedisConversationMemoryAdapter (shared, bounded, JSON round-trip, degrades on outage)")
class RedisConversationMemoryAdapterTest {

    private static final Duration TTL = Duration.ofSeconds(3600);

    private RedisConversationMemoryAdapter adapter(ConversationTurnStore store, int maxTurns) {
        return new RedisConversationMemoryAdapter(store, new ObjectMapper(), maxTurns, TTL);
    }

    @Test
    @DisplayName("recentTurns returns appended turns oldest-first, content preserved")
    void oldestFirstRoundTrip() {
        RedisConversationMemoryAdapter memory = adapter(new FakeConversationTurnStore(), 6);

        memory.append("c1", new ConversationTurn("q1", "a1"));
        memory.append("c1", new ConversationTurn("q2", "a2"));

        assertEquals(List.of(new ConversationTurn("q1", "a1"), new ConversationTurn("q2", "a2")),
                memory.recentTurns("c1"));
    }

    @Test
    @DisplayName("per-conversation history is bounded to max-turns (oldest dropped)")
    void boundedToMaxTurns() {
        RedisConversationMemoryAdapter memory = adapter(new FakeConversationTurnStore(), 2);

        memory.append("c1", new ConversationTurn("q1", "a1"));
        memory.append("c1", new ConversationTurn("q2", "a2"));
        memory.append("c1", new ConversationTurn("q3", "a3"));

        assertEquals(List.of(new ConversationTurn("q2", "a2"), new ConversationTurn("q3", "a3")),
                memory.recentTurns("c1"));
    }

    @Test
    @DisplayName("conversations are isolated by key")
    void isolatedByConversation() {
        RedisConversationMemoryAdapter memory = adapter(new FakeConversationTurnStore(), 6);

        memory.append("c1", new ConversationTurn("q1", "a1"));
        memory.append("c2", new ConversationTurn("q2", "a2"));

        assertEquals(List.of(new ConversationTurn("q1", "a1")), memory.recentTurns("c1"));
        assertEquals(List.of(new ConversationTurn("q2", "a2")), memory.recentTurns("c2"));
    }

    @Test
    @DisplayName("a blank conversation id returns empty history and appends are no-ops")
    void blankIdIsSafe() {
        RedisConversationMemoryAdapter memory = adapter(new FakeConversationTurnStore(), 6);

        memory.append("  ", new ConversationTurn("q", "a"));
        memory.append(null, new ConversationTurn("q", "a"));

        assertTrue(memory.recentTurns("  ").isEmpty());
        assertTrue(memory.recentTurns(null).isEmpty());
    }

    @Test
    @DisplayName("turns with quotes, newlines and accents survive JSON encoding")
    void specialCharactersRoundTrip() {
        RedisConversationMemoryAdapter memory = adapter(new FakeConversationTurnStore(), 6);
        ConversationTurn turn = new ConversationTurn(
                "où est ma \"facture\"?\nligne 2", "Voici l'explication : détails\ttabulés");

        memory.append("c1", turn);

        assertEquals(List.of(turn), memory.recentTurns("c1"));
    }

    @Test
    @DisplayName("append refreshes the configured idle TTL")
    void appendAppliesTtl() {
        FakeConversationTurnStore store = new FakeConversationTurnStore();
        RedisConversationMemoryAdapter memory = adapter(store, 6);

        memory.append("c1", new ConversationTurn("q", "a"));

        assertEquals(TTL, store.lastTtl);
    }

    @Test
    @DisplayName("a corrupt stored entry is skipped, surrounding valid turns still returned in order")
    void corruptEntryIsSkipped() {
        FakeConversationTurnStore store = new FakeConversationTurnStore();
        RedisConversationMemoryAdapter memory = adapter(store, 6);

        memory.append("c1", new ConversationTurn("q1", "a1"));
        // a corrupt/legacy raw entry written straight into the list (schema drift, other writer)
        store.appendTrimExpire("conversation:memory:c1", "not-json{", 6, TTL);
        memory.append("c1", new ConversationTurn("q2", "a2"));

        assertEquals(List.of(new ConversationTurn("q1", "a1"), new ConversationTurn("q2", "a2")),
                memory.recentTurns("c1"));
    }

    @Test
    @DisplayName("a Redis outage degrades to empty history without failing the turn")
    void redisOutageDegradesSafely() {
        FakeConversationTurnStore store = new FakeConversationTurnStore();
        store.failing = true;
        RedisConversationMemoryAdapter memory = adapter(store, 6);

        // append must not throw even though the store is down
        memory.append("c1", new ConversationTurn("q", "a"));
        // read must degrade to empty rather than propagate the DataAccessException
        assertTrue(memory.recentTurns("c1").isEmpty());
    }

    // Manual fake (no Mockito): in-memory list per key with LTRIM-style trimming; can simulate a
    // Redis outage by throwing the Spring DataAccessException the real client raises.
    private static final class FakeConversationTurnStore implements ConversationTurnStore {

        private final Map<String, List<String>> data = new HashMap<>();
        private Duration lastTtl;
        private boolean failing;

        @Override
        public List<String> range(String key) {
            failIfDown();
            return data.getOrDefault(key, List.of());
        }

        @Override
        public void appendTrimExpire(String key, String value, int maxItems, Duration ttl) {
            failIfDown();
            List<String> list = data.computeIfAbsent(key, k -> new ArrayList<>());
            list.add(value);
            while (list.size() > maxItems) {
                list.remove(0);
            }
            lastTtl = ttl;
        }

        private void failIfDown() {
            if (failing) {
                throw new DataAccessResourceFailureException("redis unavailable");
            }
        }
    }
}
