package com.voicesupport.domain.service;

import com.voicesupport.domain.model.AdminStats;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.TopQuestion;
import com.voicesupport.domain.port.in.AdminDashboardUseCase;
import com.voicesupport.domain.port.out.ConversationEventStore;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AdminDashboardService implements AdminDashboardUseCase {

    private static final int TOP_QUESTIONS_LIMIT = 10;
    private static final int QUESTION_MAX_LENGTH = 80;

    private final ConversationEventStore eventStore;

    public AdminDashboardService(ConversationEventStore eventStore) {
        this.eventStore = eventStore;
    }

    @Override
    public AdminStats getStats() {
        long total = eventStore.countTotal();
        long escalated = eventStore.countEscalated();
        double escalationRate = total > 0 ? (double) escalated / total * 100 : 0;
        return new AdminStats(total, escalated, roundOneDecimal(escalationRate),
                Math.round(eventStore.averageLatencyMs()), roundOneDecimal(100 - escalationRate));
    }

    @Override
    public List<ConversationEvent> getEvents(int limit) {
        List<ConversationEvent> all = eventStore.findAll();
        int start = Math.max(0, all.size() - limit);
        return List.copyOf(all.subList(start, all.size()));
    }

    @Override
    public List<TopQuestion> getTopQuestions() {
        Map<String, Long> questionCounts = new LinkedHashMap<>();
        for (ConversationEvent event : eventStore.findAll()) {
            questionCounts.merge(normalizeQuestion(event.question()), 1L, Long::sum);
        }
        return questionCounts.entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
                .limit(TOP_QUESTIONS_LIMIT)
                .map(entry -> new TopQuestion(entry.getKey(), entry.getValue()))
                .toList();
    }

    private String normalizeQuestion(String question) {
        String normalized = question.toLowerCase().trim();
        if (normalized.length() <= QUESTION_MAX_LENGTH) {
            return normalized;
        }
        return normalized.substring(0, QUESTION_MAX_LENGTH) + "...";
    }

    private double roundOneDecimal(double value) {
        return Math.round(value * 10) / 10.0;
    }
}
