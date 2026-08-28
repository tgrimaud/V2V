package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.EscalationReason;
import com.voicesupport.conversation.domain.port.in.FetchEscalationHandoffUseCase;
import com.voicesupport.shared.config.JacksonConfig;
import com.voicesupport.shared.web.security.WebSecurityMvcConfig;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.Optional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// The by-reference fetch carries customer PII, so it is api-key gated by the central
// ApiKeyAuthInterceptor (WebSecurityMvcConfig) exactly like /answer, /retrieve and /warm-up: a call
// without the matching x-api-key is rejected (401 + ErrorResponse) before the use case runs.
@WebMvcTest(EscalationHandoffController.class)
@Import({JacksonConfig.class, WebSecurityMvcConfig.class})
@TestPropertySource(properties = "voice-support.conversation.api-key=s3cret")
@DisplayName("EscalationHandoffController requires x-api-key (TASK-BE-036)")
class EscalationHandoffControllerAuthTest {

    private static final String KNOWN_ID = "handoff-known";

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        FetchEscalationHandoffUseCase fetchEscalationHandoffUseCase() {
            return handoffId -> KNOWN_ID.equals(handoffId.value())
                    ? Optional.of(EscalationHandoff.builder()
                            .channel("genesys")
                            .reason(EscalationReason.LOW_CONFIDENCE)
                            .lastUserMessage("Pourquoi ma facture a augmenté ?")
                            .createdAt(Instant.parse("2026-08-28T10:15:30Z"))
                            .build())
                    : Optional.empty();
        }
    }

    @Test
    @DisplayName("without api-key the fetch is rejected with 401 + ErrorResponse")
    void rejectedWithoutKey() throws Exception {
        mockMvc.perform(get("/api/conversation/escalation-handoffs/{id}", KNOWN_ID))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error_code").value("ERR_401"));
    }

    @Test
    @DisplayName("with a wrong api-key the fetch is rejected with 401")
    void rejectedWithWrongKey() throws Exception {
        mockMvc.perform(get("/api/conversation/escalation-handoffs/{id}", KNOWN_ID)
                        .header("x-api-key", "nope"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("with the matching api-key the audited payload is served")
    void acceptedWithKey() throws Exception {
        mockMvc.perform(get("/api/conversation/escalation-handoffs/{id}", KNOWN_ID)
                        .header("x-api-key", "s3cret"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.handoff_id").value(KNOWN_ID))
                .andExpect(jsonPath("$.reason_code").value("low_confidence"));
    }
}
