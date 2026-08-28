package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
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

import java.util.List;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// TASK-BE-037 review #4: the streaming endpoint must reject an unknown reply_mode the same way as
// batch /converse — a sanitized 400 ERR_400, resolved synchronously (the envelope is built on the
// request thread) so it never opens a stream and never echoes the rejected value.
@WebMvcTest(controllers = ConverseStreamController.class)
@Import({GlobalExceptionHandler.class, JacksonConfig.class})
@DisplayName("ConverseStreamController reply_mode validation (TASK-BE-037)")
class ConverseStreamControllerReplyModeTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseStreamUseCase converseStreamUseCase() {
            return (transcript, conversationId) -> onChunk -> GeneratedAnswer.grounded("ok", 0.9);
        }

        @Bean
        IdempotentDeliveryGuard idempotentDeliveryGuard() {
            return new IdempotentDeliveryGuard(new InMemoryDeliveryDeduplicationAdapter(1000));
        }

        @Bean
        BackendTelemetry backendTelemetry() {
            return new BackendTelemetry(new SimpleMeterRegistry());
        }

        @Bean
        ExecutorService sseStreamExecutor() {
            return new NoopExecutorService();
        }
    }

    @Test
    void an_unknown_reply_mode_is_rejected_with_a_sanitized_400_before_a_stream_opens() throws Exception {
        // GIVEN a streaming delivery carrying an unsupported reply_mode
        // WHEN it reaches /converse-stream
        MvcResult result = mockMvc.perform(post("/api/conversation/converse-stream")
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

    static class NoopExecutorService extends AbstractExecutorService {
        @Override
        public void execute(Runnable command) {
            command.run();
        }

        @Override
        public void shutdown() {
        }

        @Override
        public List<Runnable> shutdownNow() {
            return List.of();
        }

        @Override
        public boolean isShutdown() {
            return true;
        }

        @Override
        public boolean isTerminated() {
            return true;
        }

        @Override
        public boolean awaitTermination(long timeout, TimeUnit unit) {
            return true;
        }
    }
}
