package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.ChannelEnvelope;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffCommand;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import com.voicesupport.conversation.domain.port.out.EscalationHandoffPort;
import com.voicesupport.conversation.domain.service.EscalationHandoffFactory;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("EscalationHandoffService prepare (by-reference) + fetch")
class EscalationHandoffServiceTest {

    private static final Instant NOW = Instant.parse("2026-08-28T10:15:30Z");

    private final FakeEscalationHandoffPort store = new FakeEscalationHandoffPort();
    private final EscalationHandoffService service = new EscalationHandoffService(
            new EscalationHandoffFactory(), store, Clock.fixed(NOW, ZoneOffset.UTC),
            new BackendTelemetry(new SimpleMeterRegistry()));

    @Test
    void prepare_stores_the_audited_payload_and_returns_only_the_reference() {
        // GIVEN a low-confidence escalation turn carrying the customer's question (PII)
        EscalationHandoffCommand command = command("Pourquoi ma facture a augmenté ?");

        // WHEN the hand-off is prepared
        EscalationHandoffReference reference = service.prepare(command);

        // THEN only the opaque id + non-PII routing metadata leave the backend
        assertThat(reference.handoffId()).isEqualTo("handoff-1");
        assertThat(reference.reasonCode()).isEqualTo("low_confidence");
        assertThat(reference.priority()).isEqualTo("normal");
    }

    @Test
    void the_pii_stays_backend_owned_and_is_only_reachable_by_reference() {
        // GIVEN a prepared escalation whose last user message is PII
        EscalationHandoffReference reference = service.prepare(command("Mon IBAN est FR76 1234."));

        // WHEN the stored payload is fetched by the reference
        Optional<EscalationHandoff> stored = service.fetch(HandoffId.of(reference.handoffId()));

        // THEN the audited payload (incl. PII) is held in the backend store, not on the reference
        assertThat(stored).isPresent();
        assertThat(stored.orElseThrow().lastUserMessage()).isEqualTo("Mon IBAN est FR76 1234.");
        assertThat(stored.orElseThrow().createdAt()).isEqualTo(NOW);
    }

    @Test
    void fetch_of_an_unknown_reference_returns_empty() {
        // GIVEN nothing stored under the id
        // WHEN an unknown reference is fetched
        // THEN empty is returned so the endpoint can answer a sanitized 404
        assertThat(service.fetch(HandoffId.of("unknown"))).isEmpty();
    }

    private EscalationHandoffCommand command(String question) {
        ChannelEnvelope envelope = ChannelEnvelope.of(
                "genesys", "genesys-conv-9", "evt-1", "idem-1", "voice", null);
        GeneratedAnswer answer = GeneratedAnswer.fallback(
                "Je vous mets en relation avec un conseiller.", GuardrailDecision.Verdict.LOW_CONFIDENCE);
        return EscalationHandoffCommand.of(envelope, question, answer);
    }

    // Manual fake: mints deterministic ids (handoff-1, handoff-2, …) and stores by id, so the
    // reference returned by prepare is assertable and the round-trip is verifiable without Mockito.
    private static final class FakeEscalationHandoffPort implements EscalationHandoffPort {
        private final Map<String, EscalationHandoff> stored = new HashMap<>();
        private final AtomicInteger sequence = new AtomicInteger();

        @Override
        public HandoffId store(EscalationHandoff handoff) {
            HandoffId id = HandoffId.of("handoff-" + sequence.incrementAndGet());
            stored.put(id.value(), handoff);
            return id;
        }

        @Override
        public Optional<EscalationHandoff> findById(HandoffId handoffId) {
            return Optional.ofNullable(stored.get(handoffId.value()));
        }
    }
}
