package com.voicesupport.infrastructure.adapter.in.rest;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.voicesupport.domain.model.AdminStats;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.TopQuestion;
import com.voicesupport.domain.port.in.AdminDashboardUseCase;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/admin")
public class AdminDashboardController {

    private final AdminDashboardUseCase adminDashboardUseCase;

    public AdminDashboardController(AdminDashboardUseCase adminDashboardUseCase) {
        this.adminDashboardUseCase = adminDashboardUseCase;
    }

    @GetMapping("/stats")
    public ResponseEntity<AdminStatsDto> getStats() {
        return ResponseEntity.ok(AdminStatsDto.fromDomain(adminDashboardUseCase.getStats()));
    }

    @GetMapping("/events")
    public ResponseEntity<List<ConversationEventDto>> getEvents(
            @RequestParam(value = "limit", defaultValue = "50") int limit) {
        List<ConversationEventDto> events = adminDashboardUseCase.getEvents(limit).stream()
                .map(ConversationEventDto::fromDomain)
                .toList();
        return ResponseEntity.ok(events);
    }

    @GetMapping("/top-questions")
    public ResponseEntity<List<TopQuestionDto>> getTopQuestions() {
        List<TopQuestionDto> top = adminDashboardUseCase.getTopQuestions().stream()
                .map(TopQuestionDto::fromDomain)
                .toList();
        return ResponseEntity.ok(top);
    }

    public record AdminStatsDto(
            @JsonProperty("total_conversations") long totalConversations,
            @JsonProperty("escalated_count") long escalatedCount,
            @JsonProperty("escalation_rate_percent") double escalationRatePercent,
            @JsonProperty("average_latency_ms") long averageLatencyMs,
            @JsonProperty("resolution_rate_percent") double resolutionRatePercent) {

        static AdminStatsDto fromDomain(AdminStats stats) {
            return new AdminStatsDto(stats.totalConversations(), stats.escalatedCount(),
                    stats.escalationRatePercent(), stats.averageLatencyMs(), stats.resolutionRatePercent());
        }
    }

    public record ConversationEventDto(
            @JsonProperty("conversation_id") String conversationId,
            String channel,
            String question,
            String answer,
            @JsonProperty("citation_count") int citationCount,
            @JsonProperty("latency_ms") long latencyMs,
            boolean escalated) {

        static ConversationEventDto fromDomain(ConversationEvent event) {
            return new ConversationEventDto(event.conversationId(), event.channel(), event.question(),
                    event.answer(), event.citationCount(), event.latencyMs(), event.escalated());
        }
    }

    public record TopQuestionDto(String question, long count) {

        static TopQuestionDto fromDomain(TopQuestion question) {
            return new TopQuestionDto(question.question(), question.count());
        }
    }
}
