package com.voicesupport.domain.port.out;

import java.util.List;
import reactor.core.publisher.Flux;

public interface LlmStreamingPort {

    Flux<String> streamAnswer(String question, List<String> contextChunks, List<String> conversationHistory);

    Flux<String> streamAnswer(String question, List<String> contextChunks,
                              List<String> conversationHistory, String systemPrompt);
}
