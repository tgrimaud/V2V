package com.voicesupport.domain.service;

import com.voicesupport.domain.model.Conversation;
import com.voicesupport.domain.model.Conversation.Turn;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

public class QueryReformulator {

    private static final int CONTEXT_TURNS = 4;
    private static final int SHORT_QUESTION_THRESHOLD = 30;

    private static final Set<Pattern> FOLLOW_UP_INDICATORS = Set.of(
            Pattern.compile("(?i)^(et|aussi|sinon|autrement|en plus|d'accord|ok)\\b"),
            Pattern.compile("(?i)^(est[- ]ce que|c'est|ça)\\b"),
            Pattern.compile("(?i)^(oui|non|peut-être)\\b"),
            Pattern.compile("(?i)(\\?$)"),
            Pattern.compile("(?i)^(yes|no|and|also|what about)\\b")
    );

    public String reformulate(String question, Conversation conversation) {
        if (conversation == null) {
            return question;
        }

        List<Turn> recentTurns = conversation.lastTurns(CONTEXT_TURNS);
        if (recentTurns.size() < 3) {
            return question;
        }

        if (!needsReformulation(question)) {
            return question;
        }

        String previousUserQuestion = findPreviousUserQuestion(recentTurns, question);
        if (previousUserQuestion == null) {
            return question;
        }

        return previousUserQuestion + " " + question;
    }

    private boolean needsReformulation(String question) {
        if (question.length() < SHORT_QUESTION_THRESHOLD) {
            return true;
        }

        for (Pattern pattern : FOLLOW_UP_INDICATORS) {
            if (pattern.matcher(question).find()) {
                return true;
            }
        }

        return false;
    }

    private static final Set<Pattern> GREETING_ONLY = Set.of(
            Pattern.compile("(?i)^(bonjour|bonsoir|salut|coucou|hey|hello|hi|yo|bjr|slt|cc|bsr)\\s*[!.?]*$")
    );

    private String findPreviousUserQuestion(List<Turn> turns, String currentQuestion) {
        List<Turn> mostRecentFirst = new ArrayList<>(turns);
        Collections.reverse(mostRecentFirst);
        boolean skippedCurrent = false;
        for (Turn turn : mostRecentFirst) {
            if (turn.role() != Conversation.Role.USER) {
                continue;
            }
            if (!skippedCurrent && turn.text().equals(currentQuestion)) {
                skippedCurrent = true;
                continue;
            }
            if (!isGreetingOnly(turn.text())) {
                return turn.text();
            }
        }
        return null;
    }

    private boolean isGreetingOnly(String text) {
        return GREETING_ONLY.stream().anyMatch(p -> p.matcher(text.trim()).matches());
    }
}
