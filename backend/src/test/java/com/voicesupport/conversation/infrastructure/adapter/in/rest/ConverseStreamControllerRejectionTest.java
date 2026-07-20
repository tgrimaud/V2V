package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
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
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// When the SSE worker pool is saturated the executor rejects the task; the endpoint must fail fast
// with a sanitized 503 instead of queueing unboundedly or opening a stream it cannot serve.
@WebMvcTest(ConverseStreamController.class)
@Import(JacksonConfig.class)
@DisplayName("ConverseStreamController SSE contract (saturated pool)")
class ConverseStreamControllerRejectionTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseStreamUseCase converseStreamUseCase() {
            return (transcript, conversationId) -> onChunk -> GeneratedAnswer.grounded("ok", 0.9);
        }

        @Bean
        BackendTelemetry backendTelemetry() {
            return new BackendTelemetry(new SimpleMeterRegistry());
        }

        @Bean
        ExecutorService sseStreamExecutor() {
            return new RejectingExecutorService();
        }
    }

    @Test
    @DisplayName("a rejected stream submission degrades to 503, not a half-open stream")
    void rejectionYields503() throws Exception {
        mockMvc.perform(post("/api/conversation/converse-stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Bonjour\",\"channel\":\"web\"}"))
                .andExpect(status().isServiceUnavailable());
    }

    static class RejectingExecutorService extends AbstractExecutorService {
        @Override
        public void execute(Runnable command) {
            throw new RejectedExecutionException("pool saturated");
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
