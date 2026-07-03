package com.voicesupport.infrastructure.adapter.out.persistence;

import com.voicesupport.domain.model.ConversationEvent;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InMemoryConversationEventStoreTest {

    @Test
    void empty_store_returns_zero_metrics() {
        // GIVEN
        InMemoryConversationEventStore store = new InMemoryConversationEventStore();

        // WHEN / THEN
        assertEquals(0, store.countTotal());
        assertEquals(0, store.countEscalated());
        assertEquals(0.0, store.averageLatencyMs());
    }

    @Test
    void save_updates_metrics_and_returns_immutable_snapshot() {
        // GIVEN
        InMemoryConversationEventStore store = new InMemoryConversationEventStore();
        store.save(event(100, false));
        store.save(event(300, true));

        // WHEN
        List<ConversationEvent> events = store.findAll();

        // THEN
        assertEquals(2, store.countTotal());
        assertEquals(1, store.countEscalated());
        assertEquals(200.0, store.averageLatencyMs());
        assertThrows(UnsupportedOperationException.class, () -> events.add(event(500, false)));
    }

    private ConversationEvent event(long latencyMs, boolean escalated) {
        return ConversationEvent.of("conv-1", "web", "question", "answer", 1, latencyMs, escalated);
    }
}
