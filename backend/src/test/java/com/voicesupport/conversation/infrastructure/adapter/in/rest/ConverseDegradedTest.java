package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.shared.config.JacksonConfig;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.CorrelationId;
import com.voicesupport.shared.web.rest.GlobalExceptionHandler;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.in.PrepareEscalationHandoffUseCase;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.conversation.infrastructure.adapter.out.idempotency.InMemoryDeliveryDeduplicationAdapter;
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

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// When the LLM/dependency is unavailable, /converse surfaces a sanitized 503 ERR_UPSTREAM
// carrying the runtime correlation id (TASK-BE-012). The voice runtime degrades that to a safe
// spoken turn on its side; the failure stays observable and leaks no internal detail.
@WebMvcTest(controllers = ConverseController.class)
@Import({GlobalExceptionHandler.class, JacksonConfig.class})
@DisplayName("ConverseController degraded mode (upstream unavailable)")
class ConverseDegradedTest {

    private static final String LEAK_MARKER = "mistral-internal:443 timeout SECRET-key";

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseUseCase converseUseCase() {
            return (transcript, conversationId) -> {
                throw new UpstreamUnavailableException("call failed " + LEAK_MARKER);
            };
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
    }

    @Test
    @DisplayName("an upstream failure yields a sanitized 503 with the runtime correlation id and no leak")
    void upstreamFailureIsSanitized503() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/conversation/converse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Pourquoi ma facture change ?\","
                                + "\"conversation_id\":\"c1\",\"correlation_id\":\"corr-degraded\",\"channel\":\"web\"}"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error_code").value("ERR_UPSTREAM"))
                .andExpect(jsonPath("$.correlation_id").value("corr-degraded"))
                .andExpect(header().string(CorrelationId.HEADER, "corr-degraded"))
                .andReturn();

        String body = result.getResponse().getContentAsString();
        assertFalse(body.contains("mistral-internal"), "response leaked an internal host");
        assertFalse(body.contains("SECRET-key"), "response leaked a secret-like token");
    }
}
