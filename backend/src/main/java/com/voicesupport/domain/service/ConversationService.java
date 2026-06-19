package com.voicesupport.domain.service;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.Conversation;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.port.in.AskQuestionUseCase;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.VectorSearchPort;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class ConversationService implements AskQuestionUseCase {

    private static final int TOP_K = 5;
    private static final int HISTORY_WINDOW = 6;

    private final VectorSearchPort vectorSearchPort;
    private final LlmPort llmPort;
    private final EscalationDetector escalationDetector;
    private final ConversationEventStore eventStore;
    private final Map<String, Conversation> sessions = new ConcurrentHashMap<>();

    public ConversationService(VectorSearchPort vectorSearchPort, LlmPort llmPort,
                                EscalationDetector escalationDetector, ConversationEventStore eventStore) {
        this.vectorSearchPort = vectorSearchPort;
        this.llmPort = llmPort;
        this.escalationDetector = escalationDetector;
        this.eventStore = eventStore;
    }

    @Override
    public ConversationResponse ask(String conversationId, String question) {
        long startTime = System.currentTimeMillis();

        Conversation conversation = sessions.computeIfAbsent(
                conversationId, id -> new Conversation());

        conversation.addUserTurn(question);

        if (escalationDetector.shouldEscalate(question)) {
            String escalationMsg = escalationDetector.getEscalationMessage();
            conversation.addAssistantTurn(escalationMsg, List.of());
            long latency = System.currentTimeMillis() - startTime;
            eventStore.save(ConversationEvent.of(conversationId, "web", question,
                    escalationMsg, 0, latency, true));
            return new ConversationResponse(escalationMsg, List.of());
        }

        List<Citation> citations = vectorSearchPort.searchRelevant(question, TOP_K);

        List<String> contextChunks = citations.stream()
                .map(Citation::relevantText)
                .toList();

        List<String> history = conversation.lastTurns(HISTORY_WINDOW).stream()
                .map(turn -> turn.role().name() + ": " + turn.text())
                .toList();

        String answer = llmPort.generateAnswer(question, contextChunks, history);

        conversation.addAssistantTurn(answer, citations);

        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, "web", question,
                answer, citations.size(), latency, false));

        return new ConversationResponse(answer, citations);
    }
}
