package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
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
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// When a shared secret is configured, the x-api-key header must match (ADR-0021).
@WebMvcTest(ConverseController.class)
@Import(JacksonConfig.class)
@TestPropertySource(properties = "voice-support.conversation.api-key=s3cret")
@DisplayName("ConverseController REST contract (api-key required)")
class ConverseControllerApiKeyTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseUseCase converseUseCase() {
            return (transcript, conversationId) -> GeneratedAnswer.grounded("Réponse groundée.", 0.8);
        }

        @Bean
        BackendTelemetry backendTelemetry() {
            return new BackendTelemetry(new SimpleMeterRegistry());
        }
    }

    private static final String BODY = "{\"transcript\":\"Bonjour\",\"conversation_id\":\"c1\"}";

    @Test
    @DisplayName("a missing api-key is rejected with 401")
    void missingKeyRejected() throws Exception {
        mockMvc.perform(post("/api/conversation/converse")
                        .contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("a wrong api-key is rejected with 401")
    void wrongKeyRejected() throws Exception {
        mockMvc.perform(post("/api/conversation/converse")
                        .header("x-api-key", "nope")
                        .contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("the matching api-key is accepted with 200")
    void matchingKeyAccepted() throws Exception {
        mockMvc.perform(post("/api/conversation/converse")
                        .header("x-api-key", "s3cret")
                        .contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isOk());
    }
}
