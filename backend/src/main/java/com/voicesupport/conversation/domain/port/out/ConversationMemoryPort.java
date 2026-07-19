package com.voicesupport.conversation.domain.port.out;

import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;

import java.util.List;

// Outbound port for short conversation memory keyed by conversation id (TASK-BE-006).
// `recentTurns` returns the prior completed turns (oldest first, current turn excluded);
// `append` records a finished turn. Implementations bound the retained history.
public interface ConversationMemoryPort {

    List<ConversationTurn> recentTurns(String conversationId);

    void append(String conversationId, ConversationTurn turn);
}
