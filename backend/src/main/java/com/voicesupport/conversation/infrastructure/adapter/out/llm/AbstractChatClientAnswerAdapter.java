package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import org.springframework.ai.chat.client.ChatClient;

import java.util.List;
import java.util.stream.Collectors;

// Provider-agnostic base for the LLM wording step: builds a grounded system message from the
// retrieved evidence (and optional conversation history placed in the system message, not the
// user turn) and delegates generation to a Spring AI ChatClient. Concrete adapters only supply
// the provider-specific system prompt. The domain talks to AnswerGeneratorPort, never to the SDK.
public abstract class AbstractChatClientAnswerAdapter implements AnswerGeneratorPort {

    private static final String CONTEXT_PLACEHOLDER = "{context}";
    private static final String HISTORY_HEADER =
            "\n\nHistorique de la conversation (ne répète PAS de salutation si un échange a déjà eu lieu) :\n";
    private static final String SAFE_TRANSFER =
            "Je n'ai pas cette information, je vous transfère à un conseiller.";

    private final ChatClient chatClient;

    protected AbstractChatClientAnswerAdapter(ChatClient chatClient) {
        this.chatClient = chatClient;
    }

    protected abstract String systemPromptTemplate();

    @Override
    public String generate(String question, List<RetrievedEvidence> evidence, List<String> history) {
        String systemMessage = buildSystemMessage(evidence, history);
        String text = chatClient.prompt()
                .system(systemMessage)
                .user(question == null ? "" : question)
                .call()
                .content();
        return (text == null || text.isBlank()) ? SAFE_TRANSFER : text.strip();
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
