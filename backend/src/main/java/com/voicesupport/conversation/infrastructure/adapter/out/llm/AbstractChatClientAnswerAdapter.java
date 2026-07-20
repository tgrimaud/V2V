package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import org.springframework.ai.chat.client.ChatClient;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
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
    // Bounded LLM timeout pool (TASK-BE-012 medium fix): a cached pool would spawn one thread per
    // concurrent call with no ceiling, so a provider stall could exhaust threads. This caps
    // in-flight LLM calls at MAX_LLM_THREADS; excess submissions are rejected and degrade to a
    // sanitized 503 rather than piling up. The direct-handoff SynchronousQueue keeps latency low
    // under normal load (no queueing) while enforcing the ceiling under overload.
    private static final int MAX_LLM_THREADS = 16;
    // Executor timeout is a backstop above the provider HTTP read timeout (LlmConfig): the socket
    // read timeout normally fires first and closes the connection cleanly, so this only trips if
    // the client hangs before the read (DNS/connect stall) — future.cancel then abandons it.
    private static final long TIMEOUT_BACKSTOP_MS = 2_000;
    private static final ExecutorService LLM_EXECUTOR = new ThreadPoolExecutor(
            0, MAX_LLM_THREADS, 60L, TimeUnit.SECONDS, new SynchronousQueue<>(),
            runnable -> {
                Thread thread = new Thread(runnable, "llm-call");
                thread.setDaemon(true);
                return thread;
            },
            new ThreadPoolExecutor.AbortPolicy());

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
        Future<String> future;
        try {
            future = LLM_EXECUTOR.submit(() -> invoke(systemMessage, question));
        } catch (RejectedExecutionException e) {
            throw new UpstreamUnavailableException("LLM concurrency limit reached", e);
        }
        try {
            return future.get(timeoutMs + TIMEOUT_BACKSTOP_MS, TimeUnit.MILLISECONDS);
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
