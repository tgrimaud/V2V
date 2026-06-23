package com.voicesupport.infrastructure.adapter.in.rest;

import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.port.out.ConversationEventStore;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin")
public class AdminDashboardController {

    private final ConversationEventStore eventStore;

    public AdminDashboardController(ConversationEventStore eventStore) {
        this.eventStore = eventStore;
    }

    @GetMapping("/stats")
    public ResponseEntity<Map<String, Object>> getStats() {
        long total = eventStore.countTotal();
        long escalated = eventStore.countEscalated();
        double avgLatency = eventStore.averageLatencyMs();
        double escalationRate = total > 0 ? (double) escalated / total * 100 : 0;

        return ResponseEntity.ok(Map.of(
                "total_conversations", total,
                "escalated_count", escalated,
                "escalation_rate_percent", Math.round(escalationRate * 10) / 10.0,
                "average_latency_ms", Math.round(avgLatency),
                "resolution_rate_percent", Math.round((100 - escalationRate) * 10) / 10.0
        ));
    }

    @GetMapping("/events")
    public ResponseEntity<List<ConversationEvent>> getEvents(
            @RequestParam(value = "limit", defaultValue = "50") int limit) {
        List<ConversationEvent> all = eventStore.findAll();
        int start = Math.max(0, all.size() - limit);
        return ResponseEntity.ok(List.copyOf(all.subList(start, all.size())));
    }

    @GetMapping("/top-questions")
    public ResponseEntity<List<Map<String, Object>>> getTopQuestions() {
        Map<String, Long> questionCounts = new java.util.LinkedHashMap<>();
        for (ConversationEvent event : eventStore.findAll()) {
            String normalized = event.question().toLowerCase().trim();
            if (normalized.length() > 80) {
                normalized = normalized.substring(0, 80) + "...";
            }
            questionCounts.merge(normalized, 1L, Long::sum);
        }

        List<Map<String, Object>> top = questionCounts.entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
                .limit(10)
                .map(e -> Map.<String, Object>of("question", e.getKey(), "count", e.getValue()))
                .toList();

        return ResponseEntity.ok(top);
    }
}
