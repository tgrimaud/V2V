package com.voicesupport.shared.web.rest;

import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.infrastructure.adapter.in.rest.RetrievalController;
import com.voicesupport.shared.config.JacksonConfig;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.ResourceAccessException;
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

// Verifies the sanitized REST error contract (TASK-BE-012) served through the retrieve endpoint:
// bean-validation and malformed bodies map to 400, upstream failures to 503, and no internal
// exception text leaks into the response body.
@WebMvcTest(controllers = RetrievalController.class)
@Import({GlobalExceptionHandler.class, JacksonConfig.class})
@DisplayName("GlobalExceptionHandler REST error contract")
class GlobalExceptionHandlerTest {

    private static final String LEAK_MARKER = "ollama-internal:11434 refused SECRET-Dptoken";

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        GroundQueryUseCase groundQueryUseCase() {
            // Throws an upstream failure carrying sensitive-looking detail; the advice must never
            // echo it to the client. domain=restfail simulates a provider REST failure on the
            // retrieval path (e.g. embedding endpoint down) which must also map to 503.
            return (question, domain, topK, alreadyGreeted) -> {
                if ("restfail".equals(domain)) {
                    throw new ResourceAccessException("I/O error " + LEAK_MARKER);
                }
                throw new UpstreamUnavailableException("connect " + LEAK_MARKER);
            };
        }
    }

    @Test
    @DisplayName("a blank question returns 400 ERR_400 with a correlation id, not a 200/500")
    void blankQuestionReturns400() throws Exception {
        mockMvc.perform(post("/api/conversation/retrieve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"   \",\"domain\":\"billing\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error_code").value("ERR_400"))
                .andExpect(jsonPath("$.correlation_id").isNotEmpty());
    }

    @Test
    @DisplayName("a malformed JSON body returns 400 ERR_400")
    void malformedBodyReturns400() throws Exception {
        mockMvc.perform(post("/api/conversation/retrieve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{ not json "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error_code").value("ERR_400"));
    }

    @Test
    @DisplayName("an upstream failure returns a sanitized 503 ERR_UPSTREAM without leaking internal detail")
    void upstreamFailureReturns503NoLeak() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/conversation/retrieve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"Pourquoi ma facture change ?\",\"domain\":\"billing\"}"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error_code").value("ERR_UPSTREAM"))
                .andExpect(jsonPath("$.correlation_id").isNotEmpty())
                .andReturn();

        String body = result.getResponse().getContentAsString();
        assertFalse(body.contains("ollama-internal"), "response leaked an internal host");
        assertFalse(body.contains("SECRET-Dptoken"), "response leaked a secret-like token");
        assertFalse(body.contains("refused"), "response leaked upstream error text");
    }

    @Test
    @DisplayName("a provider REST failure on the retrieval path also maps to a sanitized 503 ERR_UPSTREAM")
    void restClientFailureReturns503() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/conversation/retrieve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"question\":\"Pourquoi ma facture change ?\",\"domain\":\"restfail\"}"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error_code").value("ERR_UPSTREAM"))
                .andReturn();

        assertFalse(result.getResponse().getContentAsString().contains("ollama-internal"),
                "response leaked an internal host");
    }
}
