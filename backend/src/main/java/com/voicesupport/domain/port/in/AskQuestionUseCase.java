package com.voicesupport.domain.port.in;

import com.voicesupport.domain.model.ConversationResponse;

public interface AskQuestionUseCase {

    ConversationResponse ask(String conversationId, String question);
}
