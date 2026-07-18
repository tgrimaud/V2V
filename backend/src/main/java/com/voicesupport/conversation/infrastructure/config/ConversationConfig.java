package com.voicesupport.conversation.infrastructure.config;

import com.voicesupport.conversation.application.service.RetrievalGroundingService;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.conversation.domain.service.InputGuardrail;
import com.voicesupport.conversation.domain.service.RetrievalConfidenceGuardrail;
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
}
