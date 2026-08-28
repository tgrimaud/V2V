package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.application.service.EscalationHandoffService;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.service.EscalationHandoffFactory;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.conversation.infrastructure.adapter.out.handoff.InMemoryEscalationHandoffAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.idempotency.InMemoryDeliveryDeduplicationAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletResponse;

import java.time.Clock;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

// Proves the DEC-013 by-reference contract on /converse: an escalation turn stores the audited
// payload (with PII) backend-side and emits ONLY a handoff_id + non-PII routing metadata on the
// response; the customer's question never rides the response inline. Ordinary turns carry no
// escalation_context. Uses the real service + in-memory store (manual collaborators, no Mockito).
@DisplayName("ConverseController escalation by-reference (TASK-BE-036)")
class ConverseControllerEscalationTest {

    private final InMemoryEscalationHandoffAdapter store = new InMemoryEscalationHandoffAdapter(1000);
    private final EscalationHandoffService handoffService = new EscalationHandoffService(
            new EscalationHandoffFactory(), store, Clock.systemUTC(), new BackendTelemetry(new SimpleMeterRegistry()));

    @AfterEach
    void clearContext() {
        MDC.clear();
    }

    @Test
    void an_escalation_turn_emits_a_reference_and_keeps_the_pii_backend_owned() {
        // GIVEN a turn that the guardrail blocks as low confidence (an escalation trigger)
        ConverseController controller = controllerReturning(GeneratedAnswer.fallback(
                "Je vous mets en relation avec un conseiller.", GuardrailDecision.Verdict.LOW_CONFIDENCE));
        ConverseRequest request = new ConverseRequest(
                "Pourquoi ma facture a augmenté ?", null, "corr-1", "genesys", null,
                "genesys-conv-9", "evt-1", null, "voice", null);

        // WHEN the turn is served
        ResponseEntity<ConverseResponse> response = controller.converse(request, null, new MockHttpServletResponse());

        // THEN only the by-reference token leaves the backend
        EscalationHandoffReference reference = response.getBody().escalationContext();
        assertThat(reference).isNotNull();
        assertThat(reference.handoffId()).isNotBlank();
        assertThat(reference.reasonCode()).isEqualTo("low_confidence");
        assertThat(reference.priority()).isEqualTo("normal");

        // AND the audited payload — including the customer's question (PII) — is only in the store
        Optional<EscalationHandoff> stored = store.findById(HandoffId.of(reference.handoffId()));
        assertThat(stored).isPresent();
        assertThat(stored.orElseThrow().lastUserMessage()).isEqualTo("Pourquoi ma facture a augmenté ?");
        assertThat(stored.orElseThrow().channel()).isEqualTo("genesys");
    }

    @Test
    void an_ordinary_grounded_turn_carries_no_escalation_context() {
        // GIVEN a normal grounded answer
        ConverseController controller = controllerReturning(
                GeneratedAnswer.grounded("La proration explique l'écart.", 0.83));
        ConverseRequest request = new ConverseRequest(
                "Pourquoi ma facture ?", "c1", "corr-1", "web", null, null, null, null, null, null);

        // WHEN the turn is served
        ResponseEntity<ConverseResponse> response = controller.converse(request, null, new MockHttpServletResponse());

        // THEN no hand-off is minted and escalation_context is omitted (existing contract unchanged)
        assertThat(response.getBody().escalationContext()).isNull();
        assertThat(store.findById(HandoffId.of("any"))).isEmpty();
    }

    private ConverseController controllerReturning(GeneratedAnswer answer) {
        ConverseUseCase useCase = (transcript, conversationId) -> answer;
        return new ConverseController(
                useCase,
                new IdempotentDeliveryGuard(new InMemoryDeliveryDeduplicationAdapter(1000)),
                handoffService,
                new BackendTelemetry(new SimpleMeterRegistry()),
                "");
    }
}
