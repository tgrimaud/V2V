package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.shared.config.JacksonConfig;
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
