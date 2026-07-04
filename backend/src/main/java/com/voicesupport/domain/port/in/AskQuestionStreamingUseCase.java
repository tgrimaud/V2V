package com.voicesupport.domain.port.in;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.ConversationStreamResponse;

import java.util.List;

public interface AskQuestionStreamingUseCase {

    ConversationStreamResponse askStream(String conversationId, String question);

    void seedAssistantMessage(String conversationId, String message);

    void recordCompletion(String conversationId, String question,
                          String fullAnswer, List<Citation> citations, long startTime);

    String getCurrentAgentId(String conversationId);
}
