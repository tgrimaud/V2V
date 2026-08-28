package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.in.PrepareEscalationHandoffUseCase;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.conversation.infrastructure.adapter.out.idempotency.InMemoryDeliveryDeduplicationAdapter;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

// Directly exercises the TASK-BE-037 envelope wiring in ConverseController: memory keys on the
// normalized channel envelope (external_session_id, falling back to conversation_id) and a
// duplicate delivery is not reprocessed. A capturing fake use case records the resolved key.
@DisplayName("ConverseController channel envelope wiring (TASK-BE-037)")
class ConverseControllerEnvelopeTest {

    private static final String LISTEN_PROMPT = "Je vous écoute, posez-moi votre question.";
    private static final PrepareEscalationHandoffUseCase PREPARE_HANDOFF =
            command -> EscalationHandoffReference.of(HandoffId.of("handoff-test"), command.reason());

    private final CapturingConverseUseCase useCase = new CapturingConverseUseCase();
    private final ConverseController controller = new ConverseController(
            useCase,
            new IdempotentDeliveryGuard(new InMemoryDeliveryDeduplicationAdapter(1000)),
            PREPARE_HANDOFF,
            new BackendTelemetry(new SimpleMeterRegistry()),
            "");

    @AfterEach
    void clearContext() {
        MDC.clear();
    }

    @Test
    void keys_memory_on_the_external_session_id_when_present() {
        // GIVEN a Genesys delivery carrying its external session id
        ConverseRequest request = new ConverseRequest(
                "Pourquoi ma facture ?", "conv-legacy", "corr-1", "genesys", null,
                "genesys-conv-9", "evt-1", null, "voice", null);

        // WHEN the turn is served
        controller.converse(request, null, new MockHttpServletResponse());

        // THEN memory keys on the external session id, not the legacy conversation id
        assertThat(useCase.lastConversationId).isEqualTo("genesys-conv-9");
    }

    @Test
    void falls_back_to_the_conversation_id_when_no_external_session_id() {
        // GIVEN an existing web delivery with only a conversation id (no envelope session id)
        ConverseRequest request = new ConverseRequest(
                "Bonjour", "c1", "corr-1", "web", null, null, null, null, null, null);

        // WHEN the turn is served
        controller.converse(request, null, new MockHttpServletResponse());

        // THEN behaviour is unchanged: memory keys on the conversation id
        assertThat(useCase.lastConversationId).isEqualTo("c1");
    }

    @Test
    void does_not_reprocess_a_duplicate_delivery_with_the_same_idempotency_key() {
        // GIVEN two deliveries carrying the same idempotency key
        ConverseRequest delivery = new ConverseRequest(
                "Pourquoi ma facture ?", null, "corr-1", "genesys", null,
                "genesys-conv-9", "evt-1", "idem-42", "voice", null);

        // WHEN the same delivery arrives twice
        ResponseEntity<ConverseResponse> first = controller.converse(delivery, null, new MockHttpServletResponse());
        ResponseEntity<ConverseResponse> second = controller.converse(delivery, null, new MockHttpServletResponse());

        // THEN the pipeline runs once and the duplicate gets a safe listen prompt
        assertThat(useCase.calls).isEqualTo(1);
        assertThat(first.getBody().text()).isEqualTo("La proration explique l'écart.");
        assertThat(second.getBody().text()).isEqualTo(LISTEN_PROMPT);
    }

    @Test
    void reprocesses_a_retry_with_the_same_idempotency_key_after_the_first_turn_fails() {
        // GIVEN a use case that fails the first turn then succeeds, over a real dedup guard
        var flaky = new FlakyConverseUseCase();
        var flakyController = new ConverseController(
                flaky,
                new IdempotentDeliveryGuard(new InMemoryDeliveryDeduplicationAdapter(1000)),
                PREPARE_HANDOFF,
                new BackendTelemetry(new SimpleMeterRegistry()),
                "");
        ConverseRequest delivery = new ConverseRequest(
                "Pourquoi ma facture ?", null, "corr-1", "genesys", null,
                "genesys-conv-9", "evt-1", "idem-42", "voice", null);

        // WHEN the first delivery fails and the same key is retried
        assertThatThrownBy(() -> flakyController.converse(delivery, null, new MockHttpServletResponse()))
                .isInstanceOf(UpstreamUnavailableException.class);
        ResponseEntity<ConverseResponse> retry =
                flakyController.converse(delivery, null, new MockHttpServletResponse());

        // THEN the retry is reprocessed (reservation released on failure), not swallowed as a duplicate
        assertThat(flaky.calls).isEqualTo(2);
        assertThat(retry.getBody().text()).isEqualTo("La proration explique l'écart.");
    }

    private static final class CapturingConverseUseCase implements ConverseUseCase {
        private String lastConversationId;
        private int calls;

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId) {
            return converse(transcript, conversationId, null);
        }

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId, String forcedLanguage) {
            this.lastConversationId = conversationId;
            this.calls++;
            return GeneratedAnswer.grounded("La proration explique l'écart.", 0.83);
        }
    }

    private static final class FlakyConverseUseCase implements ConverseUseCase {
        private int calls;

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId) {
            return converse(transcript, conversationId, null);
        }

        @Override
        public GeneratedAnswer converse(String transcript, String conversationId, String forcedLanguage) {
            this.calls++;
            if (calls == 1) {
                throw new UpstreamUnavailableException("upstream 503");
            }
            return GeneratedAnswer.grounded("La proration explique l'écart.", 0.83);
        }
    }
}
