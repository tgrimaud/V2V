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
    void shouldCreateNewConversationWhenLoadingUnknownId() {
        Conversation conversation = store.load("unknown");

        assertNotNull(conversation);
        assertTrue(conversation.getTurns().isEmpty());
    }

    @Test
    void shouldReturnSameConversationForSameId() {
        Conversation first = store.load("conv-1");
        first.addUserTurn("Bonjour");
        store.save("conv-1", first);

        Conversation reloaded = store.load("conv-1");

        assertEquals(1, reloaded.getTurns().size());
        assertEquals("Bonjour", reloaded.getTurns().get(0).text());
    }

    @Test
    void shouldIsolateConversationsById() {
        Conversation a = store.load("conv-a");
        a.addUserTurn("Question A");
        store.save("conv-a", a);

        Conversation b = store.load("conv-b");

        assertTrue(b.getTurns().isEmpty());
    }

    @Test
    void shouldPersistAgentRoutingAcrossLoads() {
        Conversation conversation = store.load("conv-agent");
        conversation.setCurrentAgentId("billing");
        store.save("conv-agent", conversation);

        assertEquals("billing", store.load("conv-agent").getCurrentAgentId());
    }
}
