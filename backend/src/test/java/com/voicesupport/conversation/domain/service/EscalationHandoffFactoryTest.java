package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.ChannelEnvelope;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffCommand;
import com.voicesupport.conversation.domain.model.valueobject.EscalationReason;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("EscalationHandoffFactory builds the audited payload (ADR-0019)")
class EscalationHandoffFactoryTest {

    private final EscalationHandoffFactory factory = new EscalationHandoffFactory();

    @Test
    void maps_the_command_and_reason_onto_the_full_adr_0019_payload() {
        // GIVEN a Genesys escalation turn and a fixed created_at
        ChannelEnvelope envelope = ChannelEnvelope.of(
                "genesys", "genesys-conv-9", "evt-1", "idem-1", "voice", null);
        GeneratedAnswer answer = GeneratedAnswer.fallback(
                "Je préfère vous mettre en relation avec un conseiller.", GuardrailDecision.Verdict.LOW_CONFIDENCE);
        EscalationHandoffCommand command = EscalationHandoffCommand.of(
                envelope, "Pourquoi ma facture a augmenté ?", answer);
        Instant createdAt = Instant.parse("2026-08-28T10:15:30Z");

        // WHEN the factory builds the hand-off
        EscalationHandoff handoff = factory.build(command, createdAt);

        // THEN the routing metadata comes from the reason and the context from the turn
        assertThat(handoff.channel()).isEqualTo("genesys");
        assertThat(handoff.externalSessionId()).isEqualTo("genesys-conv-9");
        assertThat(handoff.conversationId()).isEqualTo("genesys-conv-9");
        assertThat(handoff.messageId()).isEqualTo("evt-1");
        assertThat(handoff.reasonCode()).isEqualTo(EscalationReason.LOW_CONFIDENCE.code());
        assertThat(handoff.reasonLabel()).isEqualTo(EscalationReason.LOW_CONFIDENCE.label());
        assertThat(handoff.priority()).isEqualTo("normal");
        assertThat(handoff.evidenceStatus()).isEqualTo("insufficient_evidence");
        assertThat(handoff.recommendedNextAction()).isNotBlank();
        assertThat(handoff.lastUserMessage()).isEqualTo("Pourquoi ma facture a augmenté ?");
        assertThat(handoff.summary()).isEqualTo("Je préfère vous mettre en relation avec un conseiller.");
        assertThat(handoff.createdAt()).isEqualTo(createdAt);
        assertThat(handoff.citations()).isEmpty();
    }
}
