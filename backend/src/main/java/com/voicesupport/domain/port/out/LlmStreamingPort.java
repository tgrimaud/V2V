package com.voicesupport.domain.port.out;

import com.voicesupport.domain.model.TokenStream;

import java.util.List;

public interface LlmStreamingPort {

    TokenStream streamAnswer(String question, List<String> contextChunks, List<String> conversationHistory);

    TokenStream streamAnswer(String question, List<String> contextChunks,
                             List<String> conversationHistory, String systemPrompt);
}
