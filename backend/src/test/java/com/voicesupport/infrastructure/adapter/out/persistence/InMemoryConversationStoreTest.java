package com.voicesupport.infrastructure.adapter.out.persistence;

import com.voicesupport.domain.model.Conversation;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class InMemoryConversationStoreTest {

    private InMemoryConversationStore store;

    @BeforeEach
    void setUp() {
        store = new InMemoryConversationStore();
    }

    @Test
    void load_creates_new_conversation_when_id_is_unknown() {
        // WHEN
        Conversation conversation = store.load("unknown");

        // THEN
        assertNotNull(conversation);
        assertTrue(conversation.getTurns().isEmpty());
    }

    @Test
    void load_returns_same_conversation_for_same_id() {
        // GIVEN
        Conversation first = store.load("conv-1");
        first.addUserTurn("Bonjour");
        store.save("conv-1", first);

        // WHEN
        Conversation reloaded = store.load("conv-1");

        // THEN
        assertEquals(1, reloaded.getTurns().size());
        assertEquals("Bonjour", reloaded.getTurns().get(0).text());
    }

    @Test
    void load_isolates_conversations_by_id() {
        // GIVEN
        Conversation a = store.load("conv-a");
        a.addUserTurn("Question A");
        store.save("conv-a", a);

        // WHEN
        Conversation b = store.load("conv-b");

        // THEN
        assertTrue(b.getTurns().isEmpty());
    }

    @Test
    void load_persists_agent_routing_across_loads() {
        // GIVEN
        Conversation conversation = store.load("conv-agent");
        conversation.setCurrentAgentId("billing");
        store.save("conv-agent", conversation);

        // WHEN / THEN
        assertEquals("billing", store.load("conv-agent").getCurrentAgentId());
    }
}
