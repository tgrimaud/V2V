package com.voicesupport.domain.service;

import com.voicesupport.domain.model.AgentProfile;
import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.Conversation;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.model.ConversationStreamResponse;
import com.voicesupport.domain.model.GuardrailResult;
import com.voicesupport.domain.model.TokenStream;
import com.voicesupport.domain.port.in.AskQuestionUseCase;
import com.voicesupport.domain.port.in.AskQuestionStreamingUseCase;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.ConversationStore;
import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import com.voicesupport.domain.port.out.VectorSearchPort;

import java.util.List;

public class ConversationOrchestrator implements AskQuestionUseCase, AskQuestionStreamingUseCase {

    private static final int TOP_K = 5;
    private static final int HISTORY_WINDOW = 6;
    private static final String CHANNEL_WEB = "web";
    private static final String CHANNEL_VOICE = "voice";

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
        Conversation conversation = conversationStore.load(conversationId);
        boolean alreadyGreeted = conversation.hasAssistantTurn();
        conversation.addUserTurn(question);

        if (escalationDetector.shouldEscalate(question)) {
            return handleEscalation(conversation, conversationId, question, startTime, CHANNEL_WEB);
        }

        GuardrailResult preCheck = guardrailService.checkBeforeSearch(question, alreadyGreeted);
        if (preCheck.blocked()) {
            return handleBlock(conversation, conversationId, question, preCheck, List.of(),
                    isActualBlock(preCheck), startTime, CHANNEL_WEB);
        }

        AgentProfile agent = routeToAgent(question, conversation);
        List<Citation> citations = retrieve(question, conversation, agent);

        GuardrailResult postCheck = guardrailService.checkAfterSearch(question, citations);
        if (postCheck.blocked()) {
            return handleBlock(conversation, conversationId, question, postCheck, citations,
                    true, startTime, CHANNEL_WEB);
        }

        return completeAsk(conversation, conversationId, question, agent, citations, startTime);
    }

    @Override
    public ConversationStreamResponse askStream(String conversationId, String question) {
        long startTime = System.currentTimeMillis();
        Conversation conversation = conversationStore.load(conversationId);
        boolean alreadyGreeted = conversation.hasAssistantTurn();
        conversation.addUserTurn(question);

        if (escalationDetector.shouldEscalate(question)) {
            return escalatedStream(conversation, conversationId, question, startTime);
        }

        GuardrailResult preCheck = guardrailService.checkBeforeSearch(question, alreadyGreeted);
        if (preCheck.blocked()) {
            return blockedStream(conversation, conversationId, question, preCheck, List.of(),
                    isActualBlock(preCheck), startTime);
        }

        AgentProfile agent = routeToAgent(question, conversation);
        List<Citation> citations = retrieve(question, conversation, agent);

        GuardrailResult postCheck = guardrailService.checkAfterSearch(question, citations);
        if (postCheck.blocked()) {
            return blockedStream(conversation, conversationId, question, postCheck, citations, true, startTime);
        }

        return completeStream(conversation, conversationId, question, agent, citations);
    }

    private ConversationStreamResponse completeStream(Conversation conversation, String conversationId, String question,
                                                      AgentProfile agent, List<Citation> citations) {
        List<String> contextChunks = relevantTexts(citations);
        List<String> history = buildHistory(conversation);
        conversationStore.save(conversationId, conversation);

        TokenStream tokenStream = llmStreamingPort.streamAnswer(
                question, contextChunks, history, agent.systemPrompt());
        return new ConversationStreamResponse(tokenStream, citations, false, false, agent.id(), agent.name());
    }

    @Override
    public void seedAssistantMessage(String conversationId, String message) {
        if (message == null || message.isBlank()) {
            return;
        }
        Conversation conversation = conversationStore.load(conversationId);
        conversation.addAssistantTurn(message, List.of());
        conversationStore.save(conversationId, conversation);
    }

    @Override
    public void recordCompletion(String conversationId, String question,
                                  String fullAnswer, List<Citation> citations, long startTime) {
        Conversation conversation = conversationStore.load(conversationId);
        conversation.addAssistantTurn(fullAnswer, citations);
        conversationStore.save(conversationId, conversation);
        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, CHANNEL_VOICE, question,
                fullAnswer, citations.size(), latency, false));
    }

    @Override
    public String getCurrentAgentId(String conversationId) {
        return conversationStore.load(conversationId).getCurrentAgentId();
    }

    private ConversationResponse completeAsk(Conversation conversation, String conversationId, String question,
                                             AgentProfile agent, List<Citation> citations, long startTime) {
        List<String> contextChunks = relevantTexts(citations);
        List<String> history = buildHistory(conversation);
        String answer = llmPort.generateAnswer(question, contextChunks, history, agent.systemPrompt());

        conversation.addAssistantTurn(answer, citations);
        conversationStore.save(conversationId, conversation);
        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, CHANNEL_WEB, question,
                answer, citations.size(), latency, false));
        return new ConversationResponse(answer, citations, agent.id(), agent.name(), false);
    }

    private ConversationResponse handleEscalation(Conversation conversation, String conversationId,
                                                  String question, long startTime, String channel) {
        String msg = escalationDetector.getEscalationMessage();
        persistAssistantMessage(conversation, conversationId, question, msg, channel, true, startTime);
        return new ConversationResponse(msg, List.of(), null, null, false);
    }

    private ConversationResponse handleBlock(Conversation conversation, String conversationId, String question,
                                             GuardrailResult result, List<Citation> citations,
                                             boolean actualBlock, long startTime, String channel) {
        persistAssistantMessage(conversation, conversationId, question,
                result.fallbackMessage(), channel, false, startTime);
        return new ConversationResponse(result.fallbackMessage(), citations, null, null, actualBlock);
    }

    private ConversationStreamResponse escalatedStream(Conversation conversation, String conversationId,
                                                       String question, long startTime) {
        String msg = escalationDetector.getEscalationMessage();
        persistAssistantMessage(conversation, conversationId, question, msg, CHANNEL_VOICE, true, startTime);
        return new ConversationStreamResponse(TokenStream.single(msg), List.of(), true, false, null, null);
    }

    private ConversationStreamResponse blockedStream(Conversation conversation, String conversationId, String question,
                                                     GuardrailResult result, List<Citation> citations,
                                                     boolean actualBlock, long startTime) {
        persistAssistantMessage(conversation, conversationId, question,
                result.fallbackMessage(), CHANNEL_VOICE, false, startTime);
        return new ConversationStreamResponse(
                TokenStream.single(result.fallbackMessage()), citations, false, actualBlock, null, null);
    }

    private void persistAssistantMessage(Conversation conversation, String conversationId, String question,
                                         String answer, String channel, boolean escalated, long startTime) {
        conversation.addAssistantTurn(answer, List.of());
        conversationStore.save(conversationId, conversation);
        long latency = System.currentTimeMillis() - startTime;
        eventStore.save(ConversationEvent.of(conversationId, channel, question, answer, 0, latency, escalated));
    }

    private List<Citation> retrieve(String question, Conversation conversation, AgentProfile agent) {
        String searchQuery = queryReformulator.reformulate(question, conversation);
        return vectorSearchPort.searchRelevant(searchQuery, TOP_K, agent.domain());
    }

    private boolean isActualBlock(GuardrailResult result) {
        return result.verdict() != GuardrailResult.Verdict.GREETING;
    }

    private AgentProfile routeToAgent(String question, Conversation conversation) {
        AgentProfile agent = intentClassifier.classify(question, conversation.getCurrentAgentId());
        conversation.setCurrentAgentId(agent.id());
        return agent;
    }

    private List<String> relevantTexts(List<Citation> citations) {
        return citations.stream().map(Citation::relevantText).toList();
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
}
