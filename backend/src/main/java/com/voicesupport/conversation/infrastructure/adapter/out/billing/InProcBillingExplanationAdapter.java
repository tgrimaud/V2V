package com.voicesupport.conversation.infrastructure.adapter.out.billing;

import com.voicesupport.billing.domain.model.BillingExplanation;
import com.voicesupport.billing.domain.model.valueobject.BillingExplanationQuery;
import com.voicesupport.billing.domain.port.in.ExplainBillingUseCase;
import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.BillingGrounding;
import com.voicesupport.conversation.domain.model.valueobject.EscalationReason;
import com.voicesupport.conversation.domain.port.out.BillingExplanationPort;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;

import java.time.Duration;

// Outbound seam from the answer engine to the billing context (TASK-BE-045, ADR-0051), mirroring the
// knowledge retrieval seam (ADR-0027). It translates the conversation-owned request into a billing
// query, invokes the billing use case, and maps the deterministic BillingExplanation onto a
// conversation BillingGrounding (including the escalation-reason mapping) so the answer engine never
// references billing types. Records the BILLING latency slice tagged by outcome — technical
// dimensions only, never the transcript, customer reference or invoice content (privacy-safe).
public class InProcBillingExplanationAdapter implements BillingExplanationPort {

    private static final String PROVIDER = "billing";

    private final ExplainBillingUseCase explainBilling;
    private final BackendTelemetry telemetry;

    public InProcBillingExplanationAdapter(ExplainBillingUseCase explainBilling, BackendTelemetry telemetry) {
        this.explainBilling = explainBilling;
        this.telemetry = telemetry;
    }

    @Override
    public BillingGrounding explain(BillingExplanationRequest request) {
        long start = System.nanoTime();
        String outcome = "error";
        try {
            BillingExplanation explanation = explainBilling.explain(toQuery(request));
            outcome = explanation.outcome().name().toLowerCase(java.util.Locale.ROOT);
            return toGrounding(explanation);
        } finally {
            telemetry.recordLatency(Slices.BILLING, PROVIDER, outcome, Duration.ofNanos(System.nanoTime() - start));
        }
    }

    private static BillingExplanationQuery toQuery(BillingExplanationRequest request) {
        return BillingExplanationQuery.of(request.channel(), request.transcript(), request.reference(),
                request.invoiceId(), request.languageCode());
    }

    private static BillingGrounding toGrounding(BillingExplanation explanation) {
        if (explanation.answerable()) {
            return BillingGrounding.answerable(explanation.text(), explanation.confidence());
        }
        if (explanation.escalate()) {
            return BillingGrounding.escalate(explanation.text(), reasonOf(explanation.escalationCode()));
        }
        return BillingGrounding.message(explanation.text());
    }

    // Maps the billing context's stable escalation code onto the backend-owned EscalationReason
    // (ADR-0019). Kept in the infrastructure seam so neither domain depends on the other's types.
    private static EscalationReason reasonOf(String escalationCode) {
        if (BillingExplanation.CODE_IDENTITY_UNVERIFIED.equals(escalationCode)) {
            return EscalationReason.IDENTITY_UNVERIFIED;
        }
        return EscalationReason.BILLING_UNEXPLAINED;
    }
}
