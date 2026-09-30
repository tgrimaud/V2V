package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.application.service.BillingRoutingService;
import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.port.in.PrepareEscalationHandoffUseCase;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
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
import java.util.List;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;

// BUG-027 / ADR-0055: the streaming path (/converse-stream) is the real voice path and must route
// exactly like /converse. A channel-provided account + a billing question streams the deterministic
// billing chain's grounded text; no account keeps the RAG token stream.
@WebMvcTest(ConverseStreamController.class)
@Import(JacksonConfig.class)
@DisplayName("ConverseStreamController billing routing (channel-provided identity)")
class ConverseStreamControllerBillingRoutingTest {

    private static final String BILLING_TEXT = "Votre facture a augmenté de 10 €.";
    private static final String RAG_TEXT = "Réponse générique.";

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        // A billing question is always detected here; the router only routes when an account
        // reference is ALSO present (BillingRoutingService enforces the real predicate).
        @Bean
        BillingRoutingService billingTurnRouter() {
            return new BillingRoutingService(request -> GeneratedAnswer.grounded(BILLING_TEXT, 0.9), transcript -> true);
        }

        @Bean
        ConverseStreamUseCase converseStreamUseCase() {
            return (transcript, conversationId) -> streamOf(RAG_TEXT);
        }

        @Bean
        IdempotentDeliveryGuard idempotentDeliveryGuard() {
            return new IdempotentDeliveryGuard(new InMemoryDeliveryDeduplicationAdapter(1000));
        }

        @Bean
        PrepareEscalationHandoffUseCase prepareEscalationHandoffUseCase() {
            return command -> EscalationHandoffReference.of(HandoffId.of("handoff-test"), command.reason());
        }

        @Bean
        BackendTelemetry backendTelemetry() {
            return new BackendTelemetry(new SimpleMeterRegistry());
        }

        @Bean
        ExecutorService sseStreamExecutor() {
            return new InlineExecutorService();
        }

        private static TokenStream streamOf(String text) {
            return onChunk -> {
                onChunk.accept(text);
                return GeneratedAnswer.grounded(text, 0.8);
            };
        }
    }

    @Test
    @DisplayName("with a channel-provided account, a billing question streams the grounded billing text")
    void billingRouteStreamsBillingText() throws Exception {
        String body = dispatchBody(
                "{\"transcript\":\"ma facture est plus élevée\",\"conversation_id\":\"c1\","
                        + "\"channel\":\"web_voice\",\"account_id\":\"99224964\"}");

        assertTrue(body.contains("event:chunk"), body);
        assertTrue(body.contains(BILLING_TEXT), body);
        assertTrue(body.contains("event:done"), body);
        assertTrue(body.contains("\"grounded\":true"), body);
        assertFalse(body.contains(RAG_TEXT), "RAG must be bypassed on a billing turn: " + body);
    }

    @Test
    @DisplayName("without an account, the same question keeps the RAG token stream")
    void noAccountKeepsRag() throws Exception {
        String body = dispatchBody(
                "{\"transcript\":\"ma facture est plus élevée\",\"conversation_id\":\"c2\",\"channel\":\"web_voice\"}");

        assertTrue(body.contains(RAG_TEXT), body);
        assertFalse(body.contains(BILLING_TEXT), "billing must not run without an account: " + body);
    }

    private String dispatchBody(String json) throws Exception {
        MvcResult started = mockMvc.perform(post("/api/conversation/converse-stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(request().asyncStarted())
                .andReturn();
        return mockMvc.perform(asyncDispatch(started))
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
    }

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
