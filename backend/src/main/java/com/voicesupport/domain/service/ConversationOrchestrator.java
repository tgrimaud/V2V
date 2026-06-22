package com.voicesupport.domain.service;

import com.voicesupport.domain.model.AgentProfile;
import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.Conversation;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.model.GuardrailResult;
import com.voicesupport.domain.port.in.AskQuestionUseCase;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.ConversationStore;
import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import com.voicesupport.domain.port.out.VectorSearchPort;
import reactor.core.publisher.Flux;

import java.util.List;

public class ConversationOrchestrator implements AskQuestionUseCase {

    private static final int TOP_K = 5;
    private static final int HISTORY_WINDOW = 6;

    private final VectorSearchPort vectorSearchPort;
    private final LlmPort llmPort;
    private final LlmStreamingPort llmStreamingPort;
    private final EscalationDetector escalationDetector;
    private final GuardrailService guardrailService;
    private final QueryReformulator queryReformulator;
    private final IntentClassifier intentClassifier;
    private final ConversationEventStore eventStore;
    private final ConversationStore conversationStore;

    public ConversationOrchestrator(VectorSearchPort vectorSearchPort,
                                     LlmPort llmPort,
                                     LlmStreamingPort llmStreamingPort,
                                     EscalationDetector escalationDetector,
                                     GuardrailService guardrailService,
                                     QueryReformulator queryReformulator,
                                     IntentClassifier intentClassifier,
                                     ConversationEventStore eventStore,
                                     ConversationStore conversationStore) {
        this.vectorSearchPort = vectorSearchPort;
        this.llmPort = llmPort;
        this.llmStreamingPort = llmStreamingPort;
        this.escalationDetector = escalationDetector;
        this.guardrailService = guardrailService;
        this.queryReformulator = queryReformulator;
        this.intentClassifier = intentClassifier;
        this.eventStore = eventStore;
        this.conversationStore = conversationStore;
    }

    @Override
    public ConversationResponse ask(String conversationId, String question) {
        long startTime = System.currentTimeMillis();
        Conversation conversation = getOrCreateConversation(conversationId);
        conversation.addUserTurn(question);

        if (escalationDetector.shouldEscalate(question)) {
            return handleEscalation(conversation, conversationId, question, startTime, "web");
        }

        GuardrailResult preCheck = guardrailService.checkBeforeSearch(question);
        if (preCheck.blocked()) {
            return handleGuardrailBlock(conversation, conversationId, question, preCheck, startTime, "web");
        }

        AgentProfile agent = routeToAgent(question, conversation);
        String searchQuery = queryReformulator.reformulate(question, conversation);
        List<Citation> citations = vectorSearchPort.searchRelevant(searchQuery, TOP_K, agent.domain());

        GuardrailResult postCheck = guardrailService.checkAfterSearch(question, citations);
        if (postCheck.blocked()) {
            return handlePostSearchBlock(conversation, conversationId, question, postCheck, citations, startTime, "web");
        }

        List<String> contextChunks = citations.stream().map(Citation::relevantText).toList();
        List<String> history = buildHistory(conversation);

        String answer = llmPort.generateAnswer(question, contextChunks, history, agent.systemPrompt());

        conversation.addAssistantTurn(answer, citations);
        conversationStore.save(conversationId, conversation);
        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, "web", question,
                answer, citations.size(), latency, false));

        return new ConversationResponse(answer, citations, agent.id(), agent.name(), false);
    }

    public StreamingResult askStream(String conversationId, String question) {
        long startTime = System.currentTimeMillis();
        Conversation conversation = getOrCreateConversation(conversationId);
        conversation.addUserTurn(question);

        if (escalationDetector.shouldEscalate(question)) {
            String msg = escalationDetector.getEscalationMessage();
            conversation.addAssistantTurn(msg, List.of());
            conversationStore.save(conversationId, conversation);
            long latency = System.currentTimeMillis() - startTime;
            eventStore.save(ConversationEvent.of(conversationId, "voice", question, msg, 0, latency, true));
            return new StreamingResult(Flux.just(msg), List.of(), true, false, null, null);
        }

        GuardrailResult preCheck = guardrailService.checkBeforeSearch(question);
        if (preCheck.blocked()) {
            conversation.addAssistantTurn(preCheck.fallbackMessage(), List.of());
            conversationStore.save(conversationId, conversation);
            long latency = System.currentTimeMillis() - startTime;
            eventStore.save(ConversationEvent.of(conversationId, "voice", question,
                    preCheck.fallbackMessage(), 0, latency, false));
            boolean isActualBlock = preCheck.verdict() != GuardrailResult.Verdict.GREETING;
            return new StreamingResult(Flux.just(preCheck.fallbackMessage()), List.of(), false, isActualBlock, null, null);
        }

        AgentProfile agent = routeToAgent(question, conversation);
        String searchQuery = queryReformulator.reformulate(question, conversation);
        List<Citation> citations = vectorSearchPort.searchRelevant(searchQuery, TOP_K, agent.domain());

        GuardrailResult postCheck = guardrailService.checkAfterSearch(question, citations);
        if (postCheck.blocked()) {
            conversation.addAssistantTurn(postCheck.fallbackMessage(), List.of());
            conversationStore.save(conversationId, conversation);
            long latency = System.currentTimeMillis() - startTime;
            eventStore.save(ConversationEvent.of(conversationId, "voice", question,
                    postCheck.fallbackMessage(), 0, latency, false));
            return new StreamingResult(Flux.just(postCheck.fallbackMessage()), citations, false, true, null, null);
        }

        List<String> contextChunks = citations.stream().map(Citation::relevantText).toList();
        List<String> history = buildHistory(conversation);
        conversationStore.save(conversationId, conversation);

        Flux<String> tokenStream = llmStreamingPort.streamAnswer(question, contextChunks, history, agent.systemPrompt());

        return new StreamingResult(tokenStream, citations, false, false, agent.id(), agent.name());
    }

    public void recordCompletion(String conversationId, String question,
                                  String fullAnswer, List<Citation> citations, long startTime) {
        Conversation conversation = conversationStore.load(conversationId);
        conversation.addAssistantTurn(fullAnswer, citations);
        conversationStore.save(conversationId, conversation);
        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, "voice", question,
                fullAnswer, citations.size(), latency, false));
    }

    public String getCurrentAgentId(String conversationId) {
        return conversationStore.load(conversationId).getCurrentAgentId();
    }

    private AgentProfile routeToAgent(String question, Conversation conversation) {
        AgentProfile agent = intentClassifier.classify(question, conversation.getCurrentAgentId());
        conversation.setCurrentAgentId(agent.id());
        return agent;
    }

    private Conversation getOrCreateConversation(String conversationId) {
        return conversationStore.load(conversationId);
    }

    private List<String> buildHistory(Conversation conversation) {
        List<Conversation.Turn> turns = conversation.lastTurns(HISTORY_WINDOW + 1);
        if (turns.size() <= 1) {
            return List.of();
        }
        return turns.subList(0, turns.size() - 1).stream()
                .map(turn -> turn.role().name() + ": " + turn.text())
                .toList();
    }

    private ConversationResponse handleEscalation(Conversation conversation, String conversationId,
                                                   String question, long startTime, String channel) {
        String msg = escalationDetector.getEscalationMessage();
        conversation.addAssistantTurn(msg, List.of());
        conversationStore.save(conversationId, conversation);
        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, channel, question, msg, 0, latency, true));
        return new ConversationResponse(msg, List.of(), null, null, false);
    }

    private ConversationResponse handleGuardrailBlock(Conversation conversation, String conversationId,
                                                       String question, GuardrailResult result,
                                                       long startTime, String channel) {
        conversation.addAssistantTurn(result.fallbackMessage(), List.of());
        conversationStore.save(conversationId, conversation);
        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, channel, question,
                result.fallbackMessage(), 0, latency, false));
        boolean isActualBlock = result.verdict() != GuardrailResult.Verdict.GREETING;
        return new ConversationResponse(result.fallbackMessage(), List.of(), null, null, isActualBlock);
    }

    private ConversationResponse handlePostSearchBlock(Conversation conversation, String conversationId,
                                                        String question, GuardrailResult result,
                                                        List<Citation> citations, long startTime, String channel) {
        conversation.addAssistantTurn(result.fallbackMessage(), List.of());
        conversationStore.save(conversationId, conversation);
        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, channel, question,
                result.fallbackMessage(), 0, latency, false));
        return new ConversationResponse(result.fallbackMessage(), citations, null, null, true);
    }

    public record StreamingResult(Flux<String> tokens, List<Citation> citations,
                                   boolean escalated, boolean guardrailBlocked,
                                   String agentId, String agentName) {}
}
