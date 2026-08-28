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
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// TASK-BE-037 review #1: the primary voice path streams (VOICE_BACKEND_STREAM on by default), so
// /converse-stream must de-duplicate re-delivered turns just like batch /converse. A duplicate must
// short-circuit to a safe listen prompt without touching the underlying stream (no LLM, no memory).
@WebMvcTest(ConverseStreamController.class)
@Import(JacksonConfig.class)
@DisplayName("ConverseStreamController channel envelope de-duplication (TASK-BE-037)")
class ConverseStreamControllerEnvelopeTest {

    private static final String LISTEN_PROMPT = "Je vous écoute, posez-moi votre question.";
    private static final String DELIVERY = "{\"transcript\":\"Bonjour\",\"channel\":\"genesys\","
            + "\"external_session_id\":\"genesys-conv-9\",\"idempotency_key\":\"idem-dup\"}";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ConverseStreamUseCase converseStreamUseCase;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseStreamUseCase converseStreamUseCase() {
            return new CountingStreamUseCase();
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
            return new InlineExecutorService();
        }
    }

    @Test
    void a_duplicate_delivery_is_short_circuited_and_never_reaches_the_stream() throws Exception {
        // GIVEN a first Genesys streaming delivery carrying an idempotency key
        String first = dispatchBody(DELIVERY);
        assertThat(first).contains("Bonjour.");

        // WHEN the same delivery is streamed again
        String second = dispatchBody(DELIVERY);

        // THEN the duplicate gets a safe listen prompt and the underlying stream ran only once
        assertThat(second).contains(LISTEN_PROMPT);
        assertThat(((CountingStreamUseCase) converseStreamUseCase).streamCalls.get()).isEqualTo(1);
    }

    private String dispatchBody(String json) throws Exception {
        MvcResult started = mockMvc.perform(post("/api/conversation/converse-stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(request().asyncStarted())
                .andReturn();
        return mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
    }

    // Counts how many times the underlying stream is opened so the duplicate short-circuit is
    // provable: a de-duplicated delivery must add zero calls.
    static final class CountingStreamUseCase implements ConverseStreamUseCase {
        private final AtomicInteger streamCalls = new AtomicInteger();

        @Override
        public TokenStream converseStream(String transcript, String conversationId) {
            return converseStream(transcript, conversationId, null);
        }

        @Override
        public TokenStream converseStream(String transcript, String conversationId, String forcedLanguage) {
            streamCalls.incrementAndGet();
            return onChunk -> {
                onChunk.accept("Bonjour.");
                return GeneratedAnswer.grounded("Bonjour.", 0.9);
            };
        }
    }

    // Runs submitted tasks on the calling thread so the SSE body is fully buffered before dispatch.
    static class InlineExecutorService extends AbstractExecutorService {
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
