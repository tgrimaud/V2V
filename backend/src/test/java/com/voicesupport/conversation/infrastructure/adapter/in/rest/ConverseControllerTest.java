package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.shared.config.JacksonConfig;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.CorrelationId;
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

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Exercises the ADR-0021 wire contract (snake_case request fields, {text, confidence?}
// response) as served, with no api-key configured (open pilot host).
@WebMvcTest(ConverseController.class)
@Import(JacksonConfig.class)
@DisplayName("ConverseController REST contract (open)")
class ConverseControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseUseCase converseUseCase() {
            return (transcript, conversationId) -> GeneratedAnswer.grounded("La proration explique l'écart.", 0.83);
        }

        @Bean
        BackendTelemetry backendTelemetry() {
            return new BackendTelemetry(new SimpleMeterRegistry());
        }
    }

    @Test
    @DisplayName("binds the snake_case contract and returns text + confidence")
    void groundedContract() throws Exception {
        mockMvc.perform(post("/api/conversation/converse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Pourquoi ma facture change ?\","
                                + "\"conversation_id\":\"c1\",\"correlation_id\":\"corr-1\",\"channel\":\"web\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("La proration explique l'écart."))
                .andExpect(jsonPath("$.confidence").value(0.83));
    }

    @Test
    @DisplayName("echoes the runtime correlation id (from the body) on the response header")
    void echoesCorrelationIdHeader() throws Exception {
        mockMvc.perform(post("/api/conversation/converse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Pourquoi ma facture change ?\","
                                + "\"conversation_id\":\"c1\",\"correlation_id\":\"corr-42\",\"channel\":\"web\"}"))
                .andExpect(status().isOk())
                .andExpect(header().string(CorrelationId.HEADER, "corr-42"));
    }

    @Test
    @DisplayName("sanitizes a CR/LF-laced correlation id before echoing it (no header splitting / log injection) — TASK-BE-022 #3")
    void sanitizesMaliciousCorrelationIdHeader() throws Exception {
        // GIVEN a body-supplied correlation id carrying a forged extra header/log line via CR/LF
        // WHEN the turn is served
        // THEN the echoed response header is a single clean value (control chars stripped)
        mockMvc.perform(post("/api/conversation/converse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Pourquoi ma facture change ?\","
                                + "\"conversation_id\":\"c1\",\"correlation_id\":\"corr\\r\\nInjected: 1\","
                                + "\"channel\":\"web\"}"))
                .andExpect(status().isOk())
                .andExpect(header().string(CorrelationId.HEADER, "corrInjected: 1"));
    }

    @Test
    @DisplayName("a request without a conversation id is answered (stateless), not rejected")
    void missingConversationIdIsAccepted() throws Exception {
        mockMvc.perform(post("/api/conversation/converse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Pourquoi ma facture change ?\",\"channel\":\"web\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("La proration explique l'écart."));
    }

    @Test
    @DisplayName("a blank transcript returns a safe listen prompt without an amount")
    void blankTranscriptReturnsListenPrompt() throws Exception {
        mockMvc.perform(post("/api/conversation/converse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"   \",\"conversation_id\":\"c1\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("Je vous écoute, posez-moi votre question."))
                .andExpect(jsonPath("$.confidence").doesNotExist());
    }
}
