package com.voicesupport.conversation.infrastructure.adapter.out.billing;

import com.voicesupport.billing.domain.port.in.DetectBillingIntentUseCase;
import com.voicesupport.billing.domain.port.in.ExplainBillingUseCase;
import com.voicesupport.conversation.application.service.BillingAnswerService;
import com.voicesupport.conversation.application.service.BillingRoutingService;
import com.voicesupport.conversation.application.service.ConversationRoutingService;
import com.voicesupport.conversation.domain.port.in.AnswerBillingQuestionUseCase;
import com.voicesupport.conversation.domain.port.in.ConversationRoutingUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.BillingExplanationPort;
import com.voicesupport.conversation.domain.port.out.BillingIntentPort;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// Wiring for the outbound billing seam lives inside the seam package: it is the only place that
// references the billing context's published API (ExplainBillingUseCase), mirroring the knowledge
// seam (ADR-0027). Also wires the answer-engine use case that consumes the seam (ADR-0052 D3c).
@Configuration
public class BillingSeamConfig {

    @Bean
    public BillingExplanationPort billingExplanationPort(
            ExplainBillingUseCase explainBillingUseCase, BackendTelemetry telemetry) {
        return new InProcBillingExplanationAdapter(explainBillingUseCase, telemetry);
    }

    @Bean
    public AnswerBillingQuestionUseCase answerBillingQuestionUseCase(
            BillingExplanationPort billingExplanationPort,
            AnswerGeneratorPort answerGeneratorPort,
            OutputGuardrail outputGuardrail,
            LanguageDetector languageDetector) {
        return new BillingAnswerService(
                billingExplanationPort, answerGeneratorPort, outputGuardrail, languageDetector);
    }

    // Conversation-owned intent seam onto the billing published API (TASK-BE-061, ADR-0055).
    @Bean
    public BillingIntentPort billingIntentPort(DetectBillingIntentUseCase detectBillingIntentUseCase) {
        return new InProcBillingIntentAdapter(detectBillingIntentUseCase);
    }

    // Single source of truth for the RAG-vs-billing routing decision, shared by the blocking and
    // streaming paths (TASK-BE-061 / BUG-027, ADR-0055).
    @Bean
    public BillingRoutingService billingTurnRouter(
            AnswerBillingQuestionUseCase answerBillingQuestionUseCase, BillingIntentPort billingIntentPort) {
        return new BillingRoutingService(answerBillingQuestionUseCase, billingIntentPort);
    }

    // Routes a /converse turn to the billing chain (channel-provided identity + billing intent) or RAG.
    @Bean
    public ConversationRoutingUseCase conversationRoutingUseCase(
            ConverseUseCase converseUseCase,
            AnswerBillingQuestionUseCase answerBillingQuestionUseCase,
            BillingIntentPort billingIntentPort) {
        return new ConversationRoutingService(converseUseCase, answerBillingQuestionUseCase, billingIntentPort);
    }
}
