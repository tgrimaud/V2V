package com.voicesupport.infrastructure.adapter.in.rest;

import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.infrastructure.adapter.out.persistence.InMemoryConversationEventStore;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AdminDashboardControllerTest {

    @Test
    void get_stats_returns_escalation_and_latency_metrics() {
        // GIVEN
        InMemoryConversationEventStore store = new InMemoryConversationEventStore();
        store.save(event("How much?", 100, false));
        store.save(event("I want a human", 300, true));
        AdminDashboardController controller = new AdminDashboardController(store);

        // WHEN
        Map<String, Object> stats = controller.getStats().getBody();

        // THEN
        assertEquals(2L, stats.get("total_conversations"));
        assertEquals(1L, stats.get("escalated_count"));
        assertEquals(50.0, stats.get("escalation_rate_percent"));
        assertEquals(200L, stats.get("average_latency_ms"));
    }

    @Test
    void get_events_returns_last_events_by_limit() {
        // GIVEN
        InMemoryConversationEventStore store = new InMemoryConversationEventStore();
        store.save(event("first", 100, false));
        store.save(event("second", 200, false));
        AdminDashboardController controller = new AdminDashboardController(store);

        // WHEN
        List<ConversationEvent> events = controller.getEvents(1).getBody();

        // THEN
        assertEquals(1, events.size());
        assertEquals("second", events.getFirst().question());
    }

    @Test
    void get_top_questions_groups_normalized_questions() {
        // GIVEN
        InMemoryConversationEventStore store = new InMemoryConversationEventStore();
        store.save(event("  My invoice increased  ", 100, false));
        store.save(event("my invoice increased", 200, false));
        AdminDashboardController controller = new AdminDashboardController(store);

        // WHEN
        List<Map<String, Object>> topQuestions = controller.getTopQuestions().getBody();

        // THEN
        assertEquals("my invoice increased", topQuestions.getFirst().get("question"));
        assertEquals(2L, topQuestions.getFirst().get("count"));
    }

    private ConversationEvent event(String question, long latencyMs, boolean escalated) {
        return ConversationEvent.of("conv-1", "web", question, "answer", 1, latencyMs, escalated);
    }
}
