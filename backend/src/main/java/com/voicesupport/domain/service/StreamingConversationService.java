package com.voicesupport.domain.service;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.Conversation;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.GuardrailResult;
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
    private final GuardrailService guardrailService;
    private final QueryReformulator queryReformulator;
    private final ConversationEventStore eventStore;
    private final Map<String, Conversation> sessions = new ConcurrentHashMap<>();

    public StreamingConversationService(VectorSearchPort vectorSearchPort,
                                         LlmStreamingPort llmStreamingPort,
                                         EscalationDetector escalationDetector,
                                         GuardrailService guardrailService,
                                         QueryReformulator queryReformulator,
                                         ConversationEventStore eventStore) {
        this.vectorSearchPort = vectorSearchPort;
        this.llmStreamingPort = llmStreamingPort;
        this.escalationDetector = escalationDetector;
        this.guardrailService = guardrailService;
        this.queryReformulator = queryReformulator;
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
            return new StreamingResult(Flux.just(escalationMsg), List.of(), true, false);
        }

        GuardrailResult preCheck = guardrailService.checkBeforeSearch(question);
        if (preCheck.blocked()) {
            conversation.addAssistantTurn(preCheck.fallbackMessage(), List.of());
            long latency = System.currentTimeMillis() - startTime;
            eventStore.save(ConversationEvent.of(conversationId, "voice", question,
                    preCheck.fallbackMessage(), 0, latency, false));
            return new StreamingResult(Flux.just(preCheck.fallbackMessage()), List.of(), false, true);
        }

        String searchQuery = queryReformulator.reformulate(question, conversation);
        List<Citation> citations = vectorSearchPort.searchRelevant(searchQuery, TOP_K);

        GuardrailResult postCheck = guardrailService.checkAfterSearch(question, citations);
        if (postCheck.blocked()) {
            conversation.addAssistantTurn(postCheck.fallbackMessage(), List.of());
            long latency = System.currentTimeMillis() - startTime;
            eventStore.save(ConversationEvent.of(conversationId, "voice", question,
                    postCheck.fallbackMessage(), 0, latency, false));
            return new StreamingResult(Flux.just(postCheck.fallbackMessage()), citations, false, true);
        }

        List<String> contextChunks = citations.stream()
                .map(Citation::relevantText)
                .toList();

        List<String> history = conversation.lastTurns(HISTORY_WINDOW).stream()
                .map(turn -> turn.role().name() + ": " + turn.text())
                .toList();

        Flux<String> tokenStream = llmStreamingPort.streamAnswer(question, contextChunks, history);

        return new StreamingResult(tokenStream, citations, false, false);
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

    public record StreamingResult(Flux<String> tokens, List<Citation> citations,
                                   boolean escalated, boolean guardrailBlocked) {}
}
