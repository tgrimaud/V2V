package com.voicesupport.conversation.infrastructure.adapter.out.memory;

import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import com.voicesupport.conversation.domain.port.out.ConversationMemoryPort;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

// Process-local short conversation memory (TASK-BE-006). Bounded on two axes: at most
// `maxTurns` exchanges retained per conversation, and at most `maxConversations` conversations
// kept (access-ordered LRU eviction). Suitable for a single-node pilot; a shared/distributed
// store (Redis, DB) is a later concern. All access is synchronized on the backing map so
// concurrent turns on different conversations stay consistent.
public class InMemoryConversationMemoryAdapter implements ConversationMemoryPort {

    private final int maxTurns;
    private final Map<String, Deque<ConversationTurn>> store;

    public InMemoryConversationMemoryAdapter(int maxTurns, int maxConversations) {
        this.maxTurns = Math.max(1, maxTurns);
        int cap = Math.max(1, maxConversations);
        this.store = new LinkedHashMap<>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, Deque<ConversationTurn>> eldest) {
                return size() > cap;
            }
        };
    }

    @Override
    public List<ConversationTurn> recentTurns(String conversationId) {
        if (conversationId == null || conversationId.isBlank()) {
            return List.of();
        }
        synchronized (store) {
            Deque<ConversationTurn> turns = store.get(conversationId);
            return turns == null ? List.of() : List.copyOf(turns);
        }
    }

    @Override
    public void append(String conversationId, ConversationTurn turn) {
        if (conversationId == null || conversationId.isBlank() || turn == null) {
            return;
        }
        synchronized (store) {
            Deque<ConversationTurn> turns = store.computeIfAbsent(conversationId, key -> new ArrayDeque<>());
            turns.addLast(turn);
            while (turns.size() > maxTurns) {
                turns.removeFirst();
            }
        }
    }
}
