package com.voicesupport.infrastructure.adapter.in.rest;

import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.service.AdminDashboardService;
import com.voicesupport.infrastructure.adapter.out.persistence.InMemoryConversationEventStore;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AdminDashboardControllerTest {

    @Test
    void get_stats_returns_escalation_and_latency_metrics() {
        // GIVEN
        InMemoryConversationEventStore store = new InMemoryConversationEventStore();
        store.save(event("How much?", 100, false));
        store.save(event("I want a human", 300, true));
        AdminDashboardController controller = new AdminDashboardController(new AdminDashboardService(store));

        // WHEN
        AdminDashboardController.AdminStatsDto stats = controller.getStats().getBody();

        // THEN
        assertEquals(2L, stats.totalConversations());
        assertEquals(1L, stats.escalatedCount());
        assertEquals(50.0, stats.escalationRatePercent());
        assertEquals(200L, stats.averageLatencyMs());
    }

    @Test
    void get_events_returns_last_events_by_limit() {
        // GIVEN
        InMemoryConversationEventStore store = new InMemoryConversationEventStore();
        store.save(event("first", 100, false));
        store.save(event("second", 200, false));
        AdminDashboardController controller = new AdminDashboardController(new AdminDashboardService(store));

        // WHEN
        List<AdminDashboardController.ConversationEventDto> events = controller.getEvents(1).getBody();

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
        AdminDashboardController controller = new AdminDashboardController(new AdminDashboardService(store));

        // WHEN
        List<AdminDashboardController.TopQuestionDto> topQuestions = controller.getTopQuestions().getBody();

        // THEN
        assertEquals("my invoice increased", topQuestions.getFirst().question());
        assertEquals(2L, topQuestions.getFirst().count());
    }

    private ConversationEvent event(String question, long latencyMs, boolean escalated) {
        return ConversationEvent.of("conv-1", "web", question, "answer", 1, latencyMs, escalated);
    }
}
