package com.voicesupport.conversation.infrastructure.adapter.out.billing;

import com.voicesupport.billing.domain.model.BillingExplanation;
import com.voicesupport.billing.domain.model.valueobject.BillingExplanationQuery;
import com.voicesupport.billing.domain.port.in.ExplainBillingUseCase;
import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.BillingGrounding;
import com.voicesupport.conversation.domain.model.valueobject.EscalationReason;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("InProcBillingExplanationAdapter (billing -> conversation seam mapping)")
class InProcBillingExplanationAdapterTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final BackendTelemetry telemetry = new BackendTelemetry(registry);

    @Test
    void maps_an_explained_outcome_to_an_answerable_grounding() {
        // GIVEN a fully explained billing result
        BillingGrounding grounding = explain(BillingExplanation.explained("Your bill increased by 5.00 €.", 0.9));

        // THEN it is answerable with the grounded text and confidence
        assertThat(grounding.answerable()).isTrue();
        assertThat(grounding.escalate()).isFalse();
        assertThat(grounding.text()).contains("5.00 €");
        assertThat(grounding.confidence()).isEqualTo(0.9);
    }

    @Test
    void maps_identity_unresolved_to_an_identity_escalation() {
        // GIVEN an unverified-identity result
        BillingGrounding grounding = explain(BillingExplanation.identityUnresolved("Please give your reference."));

        // THEN it escalates with the IDENTITY_UNVERIFIED reason
        assertThat(grounding.escalate()).isTrue();
        assertThat(grounding.escalationReason()).isEqualTo(EscalationReason.IDENTITY_UNVERIFIED);
    }

    @Test
    void maps_not_enough_data_to_a_billing_unexplained_escalation() {
        // GIVEN a not-enough-data result
        BillingGrounding grounding = explain(BillingExplanation.notEnoughData("Not enough to compare."));

        // THEN it escalates with the BILLING_UNEXPLAINED reason
        assertThat(grounding.escalate()).isTrue();
        assertThat(grounding.escalationReason()).isEqualTo(EscalationReason.BILLING_UNEXPLAINED);
    }

    @Test
    void maps_not_a_billing_request_to_a_plain_message() {
        // GIVEN a not-a-billing-request result
        BillingGrounding grounding = explain(BillingExplanation.notABillingRequest("Which bill?"));

        // THEN it is a plain, non-escalating message
        assertThat(grounding.answerable()).isFalse();
        assertThat(grounding.escalate()).isFalse();
        assertThat(grounding.escalationReason()).isNull();
    }

    @Test
    void records_the_billing_latency_slice_tagged_by_outcome() {
        // GIVEN any explanation
        explain(BillingExplanation.explained("Your bill increased by 5.00 €.", 0.9));

        // THEN the BILLING slice timer is recorded, tagged with the outcome
        assertThat(registry.find("voice_support.slice").tag("slice", Slices.BILLING)
                .tag("outcome", "explained").timer()).isNotNull();
    }

    private BillingGrounding explain(BillingExplanation explanation) {
        InProcBillingExplanationAdapter adapter =
                new InProcBillingExplanationAdapter(new FixedExplainBilling(explanation), telemetry);
        return adapter.explain(new BillingExplanationRequest(
                "Why did my bill go up?", "EIR-1002", null, "en", "web", "conv-1", "corr-1"));
    }

    private static final class FixedExplainBilling implements ExplainBillingUseCase {
        private final BillingExplanation explanation;

        private FixedExplainBilling(BillingExplanation explanation) {
            this.explanation = explanation;
        }

        @Override
        public BillingExplanation explain(BillingExplanationQuery query) {
            return explanation;
        }
    }
}
