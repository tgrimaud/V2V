package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;

import java.util.ArrayList;
import java.util.List;

// Shared formatting of prior turns into the "Client :"/"Assistant :" lines placed in the LLM
// system message (project history lesson: history goes in the system message, current turn
// excluded). Used by both the synchronous ConversationService and the streaming counterpart so
// the two paths build identical conversation context.
public final class ConversationHistoryFormatter {

    private ConversationHistoryFormatter() {
    }

    public static List<String> format(List<ConversationTurn> turns) {
        List<String> lines = new ArrayList<>(turns.size() * 2);
        for (ConversationTurn turn : turns) {
            lines.add("Client : " + turn.userText());
            lines.add("Assistant : " + turn.assistantText());
        }
        return lines;
    }
}
