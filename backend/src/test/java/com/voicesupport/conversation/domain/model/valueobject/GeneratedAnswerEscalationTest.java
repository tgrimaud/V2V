package com.voicesupport.conversation.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("GeneratedAnswer escalation signal (TASK-BE-036)")
class GeneratedAnswerEscalationTest {

    @Test
    void a_low_confidence_fallback_carries_an_escalation_reason() {
        // GIVEN a fallback produced by a low-confidence guardrail block
        GeneratedAnswer answer = GeneratedAnswer.fallback(
                "Je préfère vous mettre en relation avec un conseiller.", GuardrailDecision.Verdict.LOW_CONFIDENCE);

        // WHEN the escalation signal is read
        // THEN the answer requires an escalation hand-off with the mapped reason
        assertThat(answer.requiresEscalation()).isTrue();
        assertThat(answer.escalation()).isEqualTo(EscalationReason.LOW_CONFIDENCE);
        assertThat(answer.grounded()).isFalse();
    }

    @Test
    void an_ungrounded_output_block_escalates_as_billing_uncertainty() {
        // GIVEN a DEC-002 output block on an ungrounded amount
        GeneratedAnswer answer = GeneratedAnswer.fallback("Montant non vérifiable.", GuardrailDecision.Verdict.UNGROUNDED);

        // THEN it escalates as a billing-uncertainty hand-off
        assertThat(answer.requiresEscalation()).isTrue();
        assertThat(answer.escalation()).isEqualTo(EscalationReason.BILLING_UNCERTAINTY);
    }

    @Test
    void a_grounded_answer_and_a_plain_fallback_never_escalate() {
        // GIVEN a grounded answer, a greeting fallback and a bare fallback
        // THEN none of them require an escalation hand-off
        assertThat(GeneratedAnswer.grounded("La proration explique l'écart.", 0.83).requiresEscalation()).isFalse();
        assertThat(GeneratedAnswer.fallback("Bonjour, je vous écoute.", GuardrailDecision.Verdict.GREETING)
                .requiresEscalation()).isFalse();
        assertThat(GeneratedAnswer.fallback("Je vous écoute.").requiresEscalation()).isFalse();
    }
}
