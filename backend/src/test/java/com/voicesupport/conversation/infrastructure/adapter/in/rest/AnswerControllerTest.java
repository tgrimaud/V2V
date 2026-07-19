package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.AnswerQuestionUseCase;
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

// Imports the production Jackson config so the snake_case request contract (top_k,
// already_greeted) is bound and the response shape is exercised as served.
@WebMvcTest(AnswerController.class)
@Import(JacksonConfig.class)
@DisplayName("AnswerController REST contract")
class AnswerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {

        @Bean
        AnswerQuestionUseCase answerQuestionUseCase() {
            return new StubAnswerQuestionUseCase();
        }
    }

    // Stub: a grounded answer for billing questions, otherwise a non-grounded fallback.
    static class StubAnswerQuestionUseCase implements AnswerQuestionUseCase {
        @Override
        public GeneratedAnswer answer(String question, String domain, int topK, boolean alreadyGreeted) {
            if (question != null && question.toLowerCase().contains("facture")) {
                return GeneratedAnswer.grounded("La proration explique l'écart.", 0.83);
            }
            return GeneratedAnswer.fallback("Cette question sort de mon domaine.");
        }
    }

    @Test
    @DisplayName("grounded answer returns text + confidence + grounded=true")
    void groundedContract() throws Exception {
        mockMvc.perform(post("/api/conversation/answer")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"Pourquoi ma facture change ?\",\"domain\":\"billing\",\"top_k\":3}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("La proration explique l'écart."))
                .andExpect(jsonPath("$.confidence").value(0.83))
                .andExpect(jsonPath("$.grounded").value(true));
    }

    @Test
    @DisplayName("fallback answer returns the safe text with null confidence and grounded=false")
    void fallbackContract() throws Exception {
        mockMvc.perform(post("/api/conversation/answer")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"Quel temps fait-il ?\",\"domain\":\"billing\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("Cette question sort de mon domaine."))
                .andExpect(jsonPath("$.confidence").doesNotExist())
                .andExpect(jsonPath("$.grounded").value(false));
    }
}
