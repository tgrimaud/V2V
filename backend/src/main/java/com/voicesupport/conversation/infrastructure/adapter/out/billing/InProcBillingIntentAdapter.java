package com.voicesupport.conversation.infrastructure.adapter.out.billing;

import com.voicesupport.billing.domain.port.in.DetectBillingIntentUseCase;
import com.voicesupport.conversation.domain.port.out.BillingIntentPort;

// Outbound seam from the answer engine to the billing intent guard (TASK-BE-061, ADR-0052/ADR-0055).
// Delegates to the billing published API so the conversation domain never references billing types;
// deterministic and side-effect free (no telemetry slice — it is a pure decision).
public class InProcBillingIntentAdapter implements BillingIntentPort {

    private final DetectBillingIntentUseCase detectBillingIntent;

    public InProcBillingIntentAdapter(DetectBillingIntentUseCase detectBillingIntent) {
        this.detectBillingIntent = detectBillingIntent;
    }

    @Override
    public boolean isBillingQuestion(String transcript) {
        return detectBillingIntent.isBillingExplanationRequest(transcript);
    }
}
