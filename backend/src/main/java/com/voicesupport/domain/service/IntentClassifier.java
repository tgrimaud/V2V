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
            } else if (score == bestScore && score > 0 && currentAgentId != null
                    && profile.id().equals(currentAgentId)) {
                bestMatch = profile;
            }
        }

        if (bestScore >= 1 && bestMatch != null) {
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
            String normalizedKeyword = keyword.toLowerCase(Locale.FRENCH);
            if (isWholeWordMatch(normalizedQuestion, normalizedKeyword)) {
                score += normalizedKeyword.contains(" ") ? 3 : 1;
            }
        }
        return score;
    }

    private boolean isWholeWordMatch(String text, String keyword) {
        int index = text.indexOf(keyword);
        while (index >= 0) {
            boolean startBoundary = (index == 0) || !Character.isLetterOrDigit(text.charAt(index - 1));
            int end = index + keyword.length();
            boolean endBoundary = (end >= text.length()) || !Character.isLetterOrDigit(text.charAt(end));
            if (!endBoundary && end < text.length()) {
                char next = text.charAt(end);
                boolean pluralSuffix = (next == 's' || next == 'x')
                        && (end + 1 >= text.length() || !Character.isLetterOrDigit(text.charAt(end + 1)));
                endBoundary = pluralSuffix;
            }
            if (startBoundary && endBoundary) {
                return true;
            }
            index = text.indexOf(keyword, index + 1);
        }
        return false;
    }
}
