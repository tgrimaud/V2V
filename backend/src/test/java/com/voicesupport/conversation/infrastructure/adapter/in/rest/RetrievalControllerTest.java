package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
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

import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Imports the production Jackson config so the snake_case contract (source_id,
// fallback_message) is exercised, not the default camelCase mapping.
@WebMvcTest(RetrievalController.class)
@Import(JacksonConfig.class)
@DisplayName("RetrievalController REST contract")
class RetrievalControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {

        @Bean
        GroundQueryUseCase groundQueryUseCase() {
            return new StubGroundQueryUseCase();
        }
    }

    // Stub returns an answerable result for billing questions, otherwise an off-topic block.
    static class StubGroundQueryUseCase implements GroundQueryUseCase {
        @Override
        public GroundingResult ground(String question, String domain, int topK, boolean alreadyGreeted) {
            if (question != null && question.toLowerCase().contains("facture")) {
                return GroundingResult.answerable(List.of(
                        new RetrievedEvidence("La proration explique l'écart", "billing-faq#1", "billing", 0.83)));
            }
            return GroundingResult.blocked(GuardrailDecision.offTopic("Hors domaine."));
        }
    }

    @Test
    @DisplayName("answerable question returns snake_case evidence with score")
    void answerableContract() throws Exception {
        mockMvc.perform(post("/api/conversation/retrieve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"Pourquoi ma facture est plus élevée ?\",\"domain\":\"billing\",\"top_k\":3}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answerable").value(true))
                .andExpect(jsonPath("$.verdict").value("PASS"))
                .andExpect(jsonPath("$.evidence[0].source_id").value("billing-faq#1"))
                .andExpect(jsonPath("$.evidence[0].domain").value("billing"))
                .andExpect(jsonPath("$.evidence[0].score").value(0.83));
    }

    @Test
    @DisplayName("blocked question returns the verdict and canned fallback, no evidence")
    void blockedContract() throws Exception {
        mockMvc.perform(post("/api/conversation/retrieve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"Quel temps fait-il ?\",\"domain\":\"billing\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answerable").value(false))
                .andExpect(jsonPath("$.verdict").value("OFF_TOPIC"))
                .andExpect(jsonPath("$.fallback_message").value("Hors domaine."))
                .andExpect(jsonPath("$.evidence").isEmpty());
    }
}
