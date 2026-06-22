package com.voicesupport.infrastructure.adapter.out.persistence;

import com.voicesupport.domain.model.Conversation;
import com.voicesupport.domain.port.out.ConversationStore;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class InMemoryConversationStore implements ConversationStore {

    private final Map<String, Conversation> sessions = new ConcurrentHashMap<>();

    @Override
    public Conversation load(String conversationId) {
        return sessions.computeIfAbsent(conversationId, id -> new Conversation());
    }

    @Override
    public void save(String conversationId, Conversation conversation) {
        sessions.put(conversationId, conversation);
    }
}
