package com.voicesupport.domain.service;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.Conversation;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import com.voicesupport.domain.port.out.VectorSearchPort;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class StreamingConversationService {

    private static final int TOP_K = 5;
    private static final int HISTORY_WINDOW = 6;

    private final VectorSearchPort vectorSearchPort;
    private final LlmStreamingPort llmStreamingPort;
    private final EscalationDetector escalationDetector;
    private final ConversationEventStore eventStore;
    private final Map<String, Conversation> sessions = new ConcurrentHashMap<>();

    public StreamingConversationService(VectorSearchPort vectorSearchPort,
                                         LlmStreamingPort llmStreamingPort,
                                         EscalationDetector escalationDetector,
                                         ConversationEventStore eventStore) {
        this.vectorSearchPort = vectorSearchPort;
        this.llmStreamingPort = llmStreamingPort;
        this.escalationDetector = escalationDetector;
        this.eventStore = eventStore;
    }

    public StreamingResult askStream(String conversationId, String question) {
        long startTime = System.currentTimeMillis();

        Conversation conversation = sessions.computeIfAbsent(
                conversationId, id -> new Conversation());
        conversation.addUserTurn(question);

        if (escalationDetector.shouldEscalate(question)) {
            String escalationMsg = escalationDetector.getEscalationMessage();
            conversation.addAssistantTurn(escalationMsg, List.of());
            long latency = System.currentTimeMillis() - startTime;
            eventStore.save(ConversationEvent.of(conversationId, "voice", question,
                    escalationMsg, 0, latency, true));
            return new StreamingResult(Flux.just(escalationMsg), List.of(), true);
        }

        List<Citation> citations = vectorSearchPort.searchRelevant(question, TOP_K);

        List<String> contextChunks = citations.stream()
                .map(Citation::relevantText)
                .toList();

        List<String> history = conversation.lastTurns(HISTORY_WINDOW).stream()
                .map(turn -> turn.role().name() + ": " + turn.text())
                .toList();

        Flux<String> tokenStream = llmStreamingPort.streamAnswer(question, contextChunks, history)
                .doOnComplete(() -> {
                    // We don't have the full answer here to save in history;
                    // the controller will handle collecting it for the done event
                });

        return new StreamingResult(tokenStream, citations, false);
    }

    public void recordCompletion(String conversationId, String question,
                                  String fullAnswer, List<Citation> citations, long startTime) {
        Conversation conversation = sessions.get(conversationId);
        if (conversation != null) {
            conversation.addAssistantTurn(fullAnswer, citations);
        }
        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, "voice", question,
                fullAnswer, citations.size(), latency, false));
    }

    public record StreamingResult(Flux<String> tokens, List<Citation> citations, boolean escalated) {}
}
