package com.voicesupport.domain.service;

import com.voicesupport.domain.model.AgentProfile;
import com.voicesupport.domain.model.AgentRegistry;

import java.util.Locale;

public class IntentClassifier {

    private final AgentRegistry agentRegistry;

    public IntentClassifier(AgentRegistry agentRegistry) {
        this.agentRegistry = agentRegistry;
    }

    public AgentProfile classify(String question, String currentAgentId) {
        String normalized = question.toLowerCase(Locale.FRENCH);

        int bestScore = 0;
        AgentProfile bestMatch = null;

        for (AgentProfile profile : agentRegistry.allProfiles()) {
            int score = computeKeywordScore(normalized, profile);
            if (score > bestScore) {
                bestScore = score;
                bestMatch = profile;
            }
        }

        if (bestScore >= 1 && bestMatch != null) {
            if (currentAgentId == null || !currentAgentId.equals(bestMatch.id())) {
                return bestMatch;
            }
            return bestMatch;
        }

        if (currentAgentId != null) {
            return agentRegistry.findById(currentAgentId)
                    .orElse(agentRegistry.getDefault());
        }

        return agentRegistry.getDefault();
    }

    private int computeKeywordScore(String normalizedQuestion, AgentProfile profile) {
        int score = 0;
        for (String keyword : profile.intentKeywords()) {
            if (normalizedQuestion.contains(keyword.toLowerCase(Locale.FRENCH))) {
                score++;
            }
        }
        return score;
    }
}
