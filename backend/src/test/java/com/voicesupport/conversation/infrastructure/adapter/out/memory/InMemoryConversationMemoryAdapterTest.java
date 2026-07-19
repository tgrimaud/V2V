package com.voicesupport.conversation.infrastructure.adapter.out.memory;

import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("InMemoryConversationMemoryAdapter (bounded, isolated, LRU)")
class InMemoryConversationMemoryAdapterTest {

    @Test
    @DisplayName("recentTurns returns appended turns oldest-first")
    void oldestFirst() {
        InMemoryConversationMemoryAdapter memory = new InMemoryConversationMemoryAdapter(6, 100);

        memory.append("c1", new ConversationTurn("q1", "a1"));
        memory.append("c1", new ConversationTurn("q2", "a2"));

        List<ConversationTurn> turns = memory.recentTurns("c1");
        assertEquals(List.of(new ConversationTurn("q1", "a1"), new ConversationTurn("q2", "a2")), turns);
    }

    @Test
    @DisplayName("per-conversation history is bounded to max-turns (oldest dropped)")
    void boundedPerConversation() {
        InMemoryConversationMemoryAdapter memory = new InMemoryConversationMemoryAdapter(2, 100);

        memory.append("c1", new ConversationTurn("q1", "a1"));
        memory.append("c1", new ConversationTurn("q2", "a2"));
        memory.append("c1", new ConversationTurn("q3", "a3"));

        assertEquals(List.of(new ConversationTurn("q2", "a2"), new ConversationTurn("q3", "a3")),
                memory.recentTurns("c1"));
    }

    @Test
    @DisplayName("a blank conversation id returns empty history and appends are no-ops")
    void blankIdIsSafe() {
        InMemoryConversationMemoryAdapter memory = new InMemoryConversationMemoryAdapter(6, 100);

        memory.append("  ", new ConversationTurn("q", "a"));
        memory.append(null, new ConversationTurn("q", "a"));

        assertTrue(memory.recentTurns("  ").isEmpty());
        assertTrue(memory.recentTurns(null).isEmpty());
    }

    @Test
    @DisplayName("conversation count is bounded: the least-recently-used conversation is evicted")
    void lruEviction() {
        InMemoryConversationMemoryAdapter memory = new InMemoryConversationMemoryAdapter(6, 2);

        memory.append("c1", new ConversationTurn("q1", "a1"));
        memory.append("c2", new ConversationTurn("q2", "a2"));
        // Touch c1 so c2 becomes the least-recently-used, then add c3 (over the cap of 2).
        memory.recentTurns("c1");
        memory.append("c3", new ConversationTurn("q3", "a3"));

        assertTrue(memory.recentTurns("c2").isEmpty());
        assertEquals(1, memory.recentTurns("c1").size());
        assertEquals(1, memory.recentTurns("c3").size());
    }
}
