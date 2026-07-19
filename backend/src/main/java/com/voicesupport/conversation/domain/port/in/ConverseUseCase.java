package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;

public interface ConverseUseCase {

    // Answers a voice/chat turn over a stateful conversation (TASK-BE-006): loads prior
    // turns for the conversation, runs the answer pipeline with that history (current turn
    // excluded), then records the new turn. First-turn greeting logic derives from empty
    // history. Returns a safe, contract-shaped answer; never an invented one.
    GeneratedAnswer converse(String transcript, String conversationId);
}
