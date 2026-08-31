package com.voicesupport.conversation.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("EscalationReason verdict mapping (ADR-0019 triggers)")
class EscalationReasonTest {

    @Test
    void maps_low_confidence_and_ungrounded_verdicts_to_escalation_reasons() {
        // GIVEN the two reactive guardrail verdicts that trigger an escalation
        // WHEN they are mapped
        // THEN each yields its backend-owned reason (low confidence -> support, ungrounded -> billing)
        assertThat(EscalationReason.fromVerdict(GuardrailDecision.Verdict.LOW_CONFIDENCE))
                .contains(EscalationReason.LOW_CONFIDENCE);
        assertThat(EscalationReason.fromVerdict(GuardrailDecision.Verdict.UNGROUNDED))
                .contains(EscalationReason.BILLING_UNCERTAINTY);
    }

    @Test
    void non_escalating_verdicts_yield_no_reason() {
        // GIVEN verdicts that are ordinary fallbacks, not human escalations
        // WHEN mapped
        // THEN no escalation reason is produced (no hand-off)
        assertThat(EscalationReason.fromVerdict(GuardrailDecision.Verdict.GREETING)).isEmpty();
        assertThat(EscalationReason.fromVerdict(GuardrailDecision.Verdict.OFF_TOPIC)).isEmpty();
        assertThat(EscalationReason.fromVerdict(GuardrailDecision.Verdict.INAPPROPRIATE)).isEmpty();
        assertThat(EscalationReason.fromVerdict(GuardrailDecision.Verdict.CLARIFY)).isEmpty();
        assertThat(EscalationReason.fromVerdict(GuardrailDecision.Verdict.PASS)).isEmpty();
        assertThat(EscalationReason.fromVerdict(null)).isEqualTo(Optional.empty());
    }

    @Test
    void exposes_the_adr_0019_routing_metadata_per_reason() {
        // GIVEN the billing-uncertainty reason
        // WHEN its routing metadata is read
        // THEN the non-PII fields carried on the reference / stored on the payload are present
        assertThat(EscalationReason.BILLING_UNCERTAINTY.code()).isEqualTo("billing_uncertainty");
        assertThat(EscalationReason.BILLING_UNCERTAINTY.priority()).isEqualTo("high");
        assertThat(EscalationReason.BILLING_UNCERTAINTY.evidenceStatus()).isEqualTo("unverified_amount");
        assertThat(EscalationReason.LOW_CONFIDENCE.priority()).isEqualTo("normal");
        assertThat(EscalationReason.LOW_CONFIDENCE.recommendedNextAction()).isNotBlank();
    }
}
