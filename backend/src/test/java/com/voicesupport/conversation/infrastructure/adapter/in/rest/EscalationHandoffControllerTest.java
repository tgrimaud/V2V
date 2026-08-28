package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.EscalationReason;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import com.voicesupport.conversation.domain.port.in.FetchEscalationHandoffUseCase;
import com.voicesupport.shared.config.JacksonConfig;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.Optional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// By-reference fetch contract (TASK-BE-036 / DEC-013): the full audited payload is served snake_case
// on a known id, and an unknown id yields the sanitized ErrorResponse (404). No api-key configured
// here (open pilot host); the gate is covered by EscalationHandoffControllerAuthTest.
@WebMvcTest(EscalationHandoffController.class)
@Import(JacksonConfig.class)
@DisplayName("EscalationHandoffController fetch-by-reference contract")
class EscalationHandoffControllerTest {

    private static final String KNOWN_ID = "handoff-known";

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        FetchEscalationHandoffUseCase fetchEscalationHandoffUseCase() {
            return handoffId -> KNOWN_ID.equals(handoffId.value())
                    ? Optional.of(sampleHandoff())
                    : Optional.empty();
        }

        private static EscalationHandoff sampleHandoff() {
            return EscalationHandoff.builder()
                    .channel("genesys")
                    .externalSessionId("genesys-conv-9")
                    .conversationId("genesys-conv-9")
                    .messageId("evt-1")
                    .reason(EscalationReason.BILLING_UNCERTAINTY)
                    .summary("Mise en relation avec un conseiller facturation.")
                    .lastUserMessage("Pourquoi ma facture a augmenté ?")
                    .createdAt(Instant.parse("2026-08-28T10:15:30Z"))
                    .build();
        }
    }

    @Test
    @DisplayName("a known reference returns the full audited payload in snake_case")
    void knownReferenceReturnsPayload() throws Exception {
        mockMvc.perform(get("/api/conversation/escalation-handoffs/{id}", KNOWN_ID))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.handoff_id").value(KNOWN_ID))
                .andExpect(jsonPath("$.channel").value("genesys"))
                .andExpect(jsonPath("$.external_session_id").value("genesys-conv-9"))
                .andExpect(jsonPath("$.reason_code").value("billing_uncertainty"))
                .andExpect(jsonPath("$.priority").value("high"))
                .andExpect(jsonPath("$.evidence_status").value("unverified_amount"))
                .andExpect(jsonPath("$.last_user_message").value("Pourquoi ma facture a augmenté ?"))
                .andExpect(jsonPath("$.created_at").value("2026-08-28T10:15:30Z"))
                .andExpect(jsonPath("$.customer_reference").doesNotExist());
    }

    @Test
    @DisplayName("an unknown reference returns the sanitized ErrorResponse (404)")
    void unknownReferenceReturns404() throws Exception {
        mockMvc.perform(get("/api/conversation/escalation-handoffs/{id}", "does-not-exist"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error_code").value("ERR_HANDOFF_NOT_FOUND"))
                .andExpect(jsonPath("$.message").exists());
    }
}
