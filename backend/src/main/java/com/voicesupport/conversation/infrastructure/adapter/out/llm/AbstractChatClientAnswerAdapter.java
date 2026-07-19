package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import org.springframework.ai.chat.client.ChatClient;

import java.util.List;
import java.util.stream.Collectors;

// Provider-agnostic base for the LLM wording step: builds a grounded system message from the
// retrieved evidence (and optional conversation history placed in the system message, not the
// user turn) and delegates generation to a Spring AI ChatClient. Concrete adapters only supply
// the provider-specific system prompt and provider name. The domain talks to AnswerGeneratorPort,
// never to the SDK. The LLM call is timed as the ADR-0018 LLM slice (TASK-BE-009).
public abstract class AbstractChatClientAnswerAdapter implements AnswerGeneratorPort {

    private static final String CONTEXT_PLACEHOLDER = "{context}";
    private static final String HISTORY_HEADER =
            "\n\nHistorique de la conversation (ne répète PAS de salutation si un échange a déjà eu lieu) :\n";

    private final ChatClient chatClient;
    private final BackendTelemetry telemetry;

    protected AbstractChatClientAnswerAdapter(ChatClient chatClient, BackendTelemetry telemetry) {
        this.chatClient = chatClient;
        this.telemetry = telemetry;
    }

    protected abstract String systemPromptTemplate();

    protected abstract String providerName();

    @Override
    public String generate(String question, List<RetrievedEvidence> evidence, List<String> history) {
        String systemMessage = buildSystemMessage(evidence, history);
        String text = telemetry.time(Slices.LLM_WORDING, providerName(),
                () -> chatClient.prompt()
                        .system(systemMessage)
                        .user(question == null ? "" : question)
                        .call()
                        .content());
        // Return the raw text (empty when the model produced nothing); classifying an empty or
        // refusal answer as a safe hand-off is the OutputGuardrail's job, so it is never voiced
        // as a grounded answer with a confidence signal.
        return text == null ? "" : text.strip();
    }

    protected String buildSystemMessage(List<RetrievedEvidence> evidence, List<String> history) {
        String context = evidence == null ? "" : evidence.stream()
                .map(RetrievedEvidence::text)
                .collect(Collectors.joining("\n---\n"));
        String systemMessage = systemPromptTemplate().replace(CONTEXT_PLACEHOLDER, context);
        if (history != null && !history.isEmpty()) {
            systemMessage += HISTORY_HEADER + String.join("\n", history);
        }
        return systemMessage;
    }
}
