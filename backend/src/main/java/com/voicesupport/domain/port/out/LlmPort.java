package com.voicesupport.domain.port.out;

import java.util.List;

public interface LlmPort {

    String generateAnswer(String question, List<String> contextChunks, List<String> conversationHistory);

    String generateAnswer(String question, List<String> contextChunks,
                          List<String> conversationHistory, String systemPrompt);
}
