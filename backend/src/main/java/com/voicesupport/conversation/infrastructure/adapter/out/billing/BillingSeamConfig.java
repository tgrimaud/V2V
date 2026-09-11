package com.voicesupport.conversation.infrastructure.adapter.out.billing;

import com.voicesupport.billing.domain.port.in.ExplainBillingUseCase;
import com.voicesupport.conversation.application.service.BillingAnswerService;
import com.voicesupport.conversation.domain.port.in.AnswerBillingQuestionUseCase;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.BillingExplanationPort;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// Wiring for the outbound billing seam lives inside the seam package: it is the only place that
// references the billing context's published API (ExplainBillingUseCase), mirroring the knowledge
// seam (ADR-0027). Also wires the answer-engine use case that consumes the seam (ADR-0051 D3c).
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
}
