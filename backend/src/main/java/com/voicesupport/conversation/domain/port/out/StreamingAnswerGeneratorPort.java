package com.voicesupport.conversation.domain.port.out;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.util.List;
import java.util.function.Consumer;

// Streaming variant of AnswerGeneratorPort (TASK-BE-007). Blocking: invokes onToken for each raw
// LLM token/chunk in order and returns when the provider stream completes. Kept separate from the
// synchronous port (interface segregation) so sync callers and fakes are unaffected; the adapter
// implements both and confines the provider's reactive stream to the infrastructure layer.
public interface StreamingAnswerGeneratorPort {

    void generate(String question, List<RetrievedEvidence> evidence, List<String> history, Consumer<String> onToken);
}
