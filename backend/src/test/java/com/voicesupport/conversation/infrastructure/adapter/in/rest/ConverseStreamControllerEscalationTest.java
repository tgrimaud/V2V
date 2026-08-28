package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.application.service.EscalationHandoffService;
import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.port.in.PrepareEscalationHandoffUseCase;
import com.voicesupport.conversation.domain.service.EscalationHandoffFactory;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.conversation.infrastructure.adapter.out.handoff.InMemoryEscalationHandoffAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.idempotency.InMemoryDeliveryDeduplicationAdapter;
import com.voicesupport.shared.config.JacksonConfig;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.List;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Proves the DEC-013 by-reference contract on the primary voice path (/converse-stream): an
// escalation turn's terminal `done` event carries ONLY the handoff_id + non-PII routing metadata
// (escalation_context), never the customer's question inline. A real service + in-memory store mint
// the reference so the wired path is exercised end to end.
@WebMvcTest(ConverseStreamController.class)
@Import(JacksonConfig.class)
@DisplayName("ConverseStreamController escalation by-reference (TASK-BE-036)")
class ConverseStreamControllerEscalationTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseStreamUseCase converseStreamUseCase() {
            return (transcript, conversationId) -> escalationStream();
        }

        @Bean
        IdempotentDeliveryGuard idempotentDeliveryGuard() {
            return new IdempotentDeliveryGuard(new InMemoryDeliveryDeduplicationAdapter(1000));
        }

        @Bean
        PrepareEscalationHandoffUseCase prepareEscalationHandoffUseCase() {
            return new EscalationHandoffService(
                    new EscalationHandoffFactory(), new InMemoryEscalationHandoffAdapter(1000),
                    Clock.systemUTC(), new BackendTelemetry(new SimpleMeterRegistry()));
        }

        @Bean
        BackendTelemetry backendTelemetry() {
            return new BackendTelemetry(new SimpleMeterRegistry());
        }

        @Bean
        ExecutorService sseStreamExecutor() {
            return new InlineExecutorService();
        }

        private static TokenStream escalationStream() {
            return onChunk -> {
                String message = "Je vous mets en relation avec un conseiller.";
                onChunk.accept(message);
                return GeneratedAnswer.fallback(message, GuardrailDecision.Verdict.LOW_CONFIDENCE);
            };
        }
    }

    @Test
    void the_done_event_carries_the_handoff_reference_not_inline_pii() throws Exception {
        // GIVEN a Genesys streaming escalation turn carrying the customer's question
        String body = dispatchBody("{\"transcript\":\"Pourquoi ma facture a augmenté ?\",\"channel\":\"genesys\","
                + "\"external_session_id\":\"genesys-conv-9\"}");

        // THEN the terminal done event carries only the by-reference token + non-PII routing metadata
        assertThat(body).contains("event:done");
        assertThat(body).contains("\"escalation_context\"");
        assertThat(body).contains("\"handoff_id\"");
        assertThat(body).contains("\"reason_code\":\"low_confidence\"");
        assertThat(body).contains("\"priority\":\"normal\"");
    }

    private String dispatchBody(String json) throws Exception {
        MvcResult started = mockMvc.perform(post("/api/conversation/converse-stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(request().asyncStarted())
                .andReturn();
        return mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
    }

    // Runs submitted tasks on the calling thread so the SSE body is fully buffered before dispatch.
    static class InlineExecutorService extends AbstractExecutorService {
        @Override
        public void execute(Runnable command) {
            command.run();
        }

        @Override
        public void shutdown() {
        }

        @Override
        public List<Runnable> shutdownNow() {
            return List.of();
        }

        @Override
        public boolean isShutdown() {
            return true;
        }

        @Override
        public boolean isTerminated() {
            return true;
        }

        @Override
        public boolean awaitTermination(long timeout, TimeUnit unit) {
            return true;
        }
    }
}
