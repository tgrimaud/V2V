package com.voicesupport.domain.model;

public record AdminStats(
        long totalConversations,
        long escalatedCount,
        double escalationRatePercent,
        long averageLatencyMs,
        double resolutionRatePercent
) {}
