package com.voicesupport.infrastructure.adapter.out.llm;

import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

public abstract class AbstractChatClientLlmAdapter implements LlmPort, LlmStreamingPort {

    private static final Logger log = LoggerFactory.getLogger(AbstractChatClientLlmAdapter.class);

    private static final String HISTORY_HEADER =
            "\n\nHistorique de la conversation (ne répète PAS de salutation si un 'Bonjour' apparaît déjà) :\n";

    private final ChatClient chatClient;

    protected AbstractChatClientLlmAdapter(ChatClient chatClient) {
        this.chatClient = chatClient;
    }

    protected abstract String defaultSystemPrompt();

    @Override
    public String generateAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
        return generateAnswer(question, contextChunks, conversationHistory, null);
    }

    @Override
    public String generateAnswer(String question, List<String> contextChunks,
                                 List<String> conversationHistory, String systemPrompt) {
        String systemMessage = buildSystemMessage(contextChunks, conversationHistory, systemPrompt);
        return chatClient.prompt()
                .system(systemMessage)
                .user(question)
                .call()
                .content();
    }

    @Override
    public Flux<String> streamAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
        return streamAnswer(question, contextChunks, conversationHistory, null);
    }

    @Override
    public Flux<String> streamAnswer(String question, List<String> contextChunks,
                                     List<String> conversationHistory, String systemPrompt) {
        String systemMessage = buildSystemMessage(contextChunks, conversationHistory, systemPrompt);
        return Flux.defer(() -> streamWithLatencyLogging(systemMessage, question));
    }

    protected String buildSystemMessage(List<String> contextChunks, List<String> conversationHistory,
                                        String systemPrompt) {
        String context = String.join("\n---\n", contextChunks);
        String prompt = systemPrompt != null ? systemPrompt : defaultSystemPrompt();
        String systemMessage = prompt.replace("{context}", context);
        if (!conversationHistory.isEmpty()) {
            systemMessage += HISTORY_HEADER + String.join("\n", conversationHistory);
        }
        return systemMessage;
    }

    private Flux<String> streamWithLatencyLogging(String systemMessage, String question) {
        long startNanos = System.nanoTime();
        AtomicBoolean firstToken = new AtomicBoolean(true);
        return chatClient.prompt()
                .system(systemMessage)
                .user(question)
                .stream()
                .content()
                .doOnNext(token -> logFirstToken(firstToken, startNanos))
                .doOnComplete(() -> log.info("[LATENCY] step=llm_total ms={}", elapsedMs(startNanos)));
    }

    private void logFirstToken(AtomicBoolean firstToken, long startNanos) {
        if (firstToken.compareAndSet(true, false)) {
            log.info("[LATENCY] step=llm_first_token ms={}", elapsedMs(startNanos));
        }
    }

    private long elapsedMs(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }
}
