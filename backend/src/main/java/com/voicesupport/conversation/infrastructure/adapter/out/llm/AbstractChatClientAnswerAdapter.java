package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import org.springframework.ai.chat.client.ChatClient;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.stream.Collectors;

// Provider-agnostic base for the LLM wording step: builds a grounded system message from the
// retrieved evidence (and optional conversation history placed in the system message, not the
// user turn) and delegates generation to a Spring AI ChatClient. Concrete adapters only supply
// the provider-specific system prompt and provider name. The domain talks to AnswerGeneratorPort,
// never to the SDK. The LLM call is timed as the ADR-0018 LLM slice (TASK-BE-009) and bounded by
// a hard timeout so a slow/hung provider degrades to a sanitized 503 (TASK-BE-012).
public abstract class AbstractChatClientAnswerAdapter implements AnswerGeneratorPort {

    private static final String CONTEXT_PLACEHOLDER = "{context}";
    private static final String HISTORY_HEADER =
            "\n\nHistorique de la conversation (ne répète PAS de salutation si un échange a déjà eu lieu) :\n";
    private static final ExecutorService LLM_EXECUTOR = Executors.newCachedThreadPool(runnable -> {
        Thread thread = new Thread(runnable, "llm-call");
        thread.setDaemon(true);
        return thread;
    });

    private final ChatClient chatClient;
    private final BackendTelemetry telemetry;
    private final long timeoutMs;

    protected AbstractChatClientAnswerAdapter(ChatClient chatClient, BackendTelemetry telemetry, long timeoutMs) {
        this.chatClient = chatClient;
        this.telemetry = telemetry;
        this.timeoutMs = timeoutMs;
    }

    protected abstract String systemPromptTemplate();

    protected abstract String providerName();

    @Override
    public String generate(String question, List<RetrievedEvidence> evidence, List<String> history) {
        String systemMessage = buildSystemMessage(evidence, history);
        String text = telemetry.time(Slices.LLM_WORDING, providerName(),
                () -> callProvider(systemMessage, question == null ? "" : question));
        // Return the raw text (empty when the model produced nothing); classifying an empty or
        // refusal answer as a safe hand-off is the OutputGuardrail's job, so it is never voiced
        // as a grounded answer with a confidence signal.
        return text == null ? "" : text.strip();
    }

    private String callProvider(String systemMessage, String question) {
        if (timeoutMs <= 0) {
            return invoke(systemMessage, question);
        }
        Future<String> future = LLM_EXECUTOR.submit(() -> invoke(systemMessage, question));
        try {
            return future.get(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw new UpstreamUnavailableException("LLM provider timed out after " + timeoutMs + " ms", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new UpstreamUnavailableException("LLM call interrupted", e);
        } catch (java.util.concurrent.ExecutionException e) {
            throw new UpstreamUnavailableException("LLM provider call failed", e.getCause());
        }
    }

    private String invoke(String systemMessage, String question) {
        return chatClient.prompt().system(systemMessage).user(question).call().content();
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
