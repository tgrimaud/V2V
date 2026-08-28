package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.conversation.infrastructure.adapter.out.idempotency.InMemoryDeliveryDeduplicationAdapter;
import com.voicesupport.shared.config.JacksonConfig;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.web.rest.GlobalExceptionHandler;
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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// TASK-BE-037 review #4: an unknown reply_mode is a caller error. It must map to a sanitized 400
// ERR_400 with a generic message, never echoing the rejected value (log/response injection guard).
@WebMvcTest(controllers = ConverseController.class)
@Import({GlobalExceptionHandler.class, JacksonConfig.class})
@DisplayName("ConverseController reply_mode validation (TASK-BE-037)")
class ConverseControllerReplyModeTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseUseCase converseUseCase() {
            return (transcript, conversationId) -> GeneratedAnswer.grounded("ok", 0.8);
        }

        @Bean
        IdempotentDeliveryGuard idempotentDeliveryGuard() {
            return new IdempotentDeliveryGuard(new InMemoryDeliveryDeduplicationAdapter(1000));
        }

        @Bean
        BackendTelemetry backendTelemetry() {
            return new BackendTelemetry(new SimpleMeterRegistry());
        }
    }

    @Test
    void an_unknown_reply_mode_is_rejected_with_a_sanitized_400() throws Exception {
        // GIVEN a delivery carrying an unsupported reply_mode
        // WHEN it reaches /converse
        MvcResult result = mockMvc.perform(post("/api/conversation/converse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Bonjour\",\"channel\":\"genesys\","
                                + "\"reply_mode\":\"smoke-signal\"}"))
                // THEN it is a generic 400 ERR_400 that never echoes the rejected value
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error_code").value("ERR_400"))
                .andExpect(jsonPath("$.message").value("The request is invalid."))
                .andReturn();

        assertFalse(result.getResponse().getContentAsString().contains("smoke-signal"),
                "response echoed the rejected reply_mode");
    }
}
