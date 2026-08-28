package com.voicesupport.conversation.domain.model.valueobject;

// streamWarmed covers the reactive LLM streaming path (converse-stream), which uses a distinct HTTP
// client + reactive pipeline from the synchronous call path, so it must be warmed on its own to
// keep the first real converse-stream turn off the cold path (TASK-BE-020). When streaming warm-up
// is disabled by config it is reported warmed (nothing left cold by us) so fullyWarmed stays honest.
public record WarmUpResult(boolean embeddingWarmed, boolean llmWarmed, boolean streamWarmed, long durationMs) {

    public boolean fullyWarmed() {
        return embeddingWarmed && llmWarmed && streamWarmed;
    }
}
