package com.voicesupport.conversation.infrastructure.config;

import com.voicesupport.conversation.application.service.AnswerService;
import com.voicesupport.conversation.application.service.ConversationService;
import com.voicesupport.conversation.application.service.RetrievalGroundingService;
import com.voicesupport.conversation.domain.port.in.AnswerQuestionUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.ConversationMemoryPort;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.conversation.domain.service.InputGuardrail;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.domain.service.RetrievalConfidenceGuardrail;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.InMemoryConversationMemoryAdapter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ConversationConfig {

    @Bean
    public InputGuardrail inputGuardrail() {
        return new InputGuardrail();
    }

    @Bean
    public RetrievalConfidenceGuardrail retrievalConfidenceGuardrail(
            @Value("${voice-support.conversation.confidence-threshold:0.5}") double confidenceThreshold) {
        return new RetrievalConfidenceGuardrail(confidenceThreshold);
    }

    @Bean
    public GroundQueryUseCase groundQueryUseCase(
            InputGuardrail inputGuardrail,
            RetrievalConfidenceGuardrail retrievalConfidenceGuardrail,
            KnowledgeRetrievalPort knowledgeRetrievalPort) {
        return new RetrievalGroundingService(inputGuardrail, retrievalConfidenceGuardrail, knowledgeRetrievalPort);
    }

    @Bean
    public OutputGuardrail outputGuardrail() {
        return new OutputGuardrail();
    }

    @Bean
    public AnswerQuestionUseCase answerQuestionUseCase(
            GroundQueryUseCase groundQueryUseCase,
            AnswerGeneratorPort answerGeneratorPort,
            OutputGuardrail outputGuardrail) {
        return new AnswerService(groundQueryUseCase, answerGeneratorPort, outputGuardrail);
    }

    @Bean
    public ConversationMemoryPort conversationMemoryPort(
            @Value("${voice-support.conversation.memory.max-turns:6}") int maxTurns,
            @Value("${voice-support.conversation.memory.max-conversations:10000}") int maxConversations) {
        return new InMemoryConversationMemoryAdapter(maxTurns, maxConversations);
    }

    @Bean
    public ConverseUseCase converseUseCase(
            AnswerQuestionUseCase answerQuestionUseCase,
            ConversationMemoryPort conversationMemoryPort) {
        return new ConversationService(answerQuestionUseCase, conversationMemoryPort);
    }
}
