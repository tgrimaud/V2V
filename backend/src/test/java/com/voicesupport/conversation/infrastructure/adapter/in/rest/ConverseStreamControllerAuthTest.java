package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.conversation.infrastructure.adapter.out.idempotency.InMemoryDeliveryDeduplicationAdapter;
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

import java.util.List;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Same endpoint with an api-key configured: a request without the matching x-api-key header is
// rejected synchronously (401) before any stream is opened.
@WebMvcTest(ConverseStreamController.class)
@Import(JacksonConfig.class)
@TestPropertySource(properties = "voice-support.conversation.api-key=secret")
@DisplayName("ConverseStreamController SSE contract (api-key enforced)")
class ConverseStreamControllerAuthTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseStreamUseCase converseStreamUseCase() {
            return (transcript, conversationId) -> streamOf();
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

        private static TokenStream streamOf() {
            return onChunk -> GeneratedAnswer.grounded("ok", 0.9);
        }
    }

    @Test
    @DisplayName("without the matching x-api-key the request is rejected with 401")
    void rejectsMissingApiKey() throws Exception {
        mockMvc.perform(post("/api/conversation/converse-stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Bonjour\",\"channel\":\"web\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("with the matching x-api-key the stream is opened (async started)")
    void acceptsMatchingApiKey() throws Exception {
        mockMvc.perform(post("/api/conversation/converse-stream")
                        .header("x-api-key", "secret")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Bonjour\",\"channel\":\"web\"}"))
                .andExpect(request().asyncStarted());
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
