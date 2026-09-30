package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.RoutableTurn;

// Entry point for a /converse turn that may be a billing question (TASK-BE-061, ADR-0055). Routes to
// the deterministic billing chain when the channel supplied an account reference AND the turn is a
// billing question; otherwise answers via the RAG pipeline. Always returns a safe, contract-shaped
// answer (fail-closed on the billing branch).
public interface ConversationRoutingUseCase {

    GeneratedAnswer answer(RoutableTurn turn);
}
