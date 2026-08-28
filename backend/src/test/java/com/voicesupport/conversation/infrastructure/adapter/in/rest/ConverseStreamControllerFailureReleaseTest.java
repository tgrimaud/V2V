package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.conversation.infrastructure.adapter.out.idempotency.InMemoryDeliveryDeduplicationAdapter;
import com.voicesupport.shared.config.JacksonConfig;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
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

// TASK-BE-037 re-review residual #1: mirrors the batch failure-release test on the streaming path.
// The primary voice path streams (VOICE_BACKEND_STREAM on by default), so a /converse-stream turn
// that fails must RELEASE its idempotency reservation (ConverseStreamSession.run()'s
// releaseReservationIfUnfinished, gated by the `reserved` flag) so a legitimate retry with the same
// key is reprocessed; while a successful turn keeps the reservation and short-circuits a duplicate.
@WebMvcTest(ConverseStreamController.class)
@Import(JacksonConfig.class)
@DisplayName("ConverseStreamController failure-release + happy-path dedup (TASK-BE-037)")
class ConverseStreamControllerFailureReleaseTest {

    private static final String LISTEN_PROMPT = "Je vous écoute, posez-moi votre question.";
    private static final String ANSWER = "La proration explique l'écart.";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ConverseStreamUseCase converseStreamUseCase;

    @BeforeEach
    void resetFake() {
        flaky().reset();
    }

    @Test
    void a_retry_with_the_same_key_is_reprocessed_after_the_first_stream_fails() throws Exception {
        // GIVEN the first streamed turn fails, then the same idempotency key is re-delivered
        flaky().failNext(1);
        String delivery = delivery("idem-retry");

        // WHEN the failing delivery is followed by a retry carrying the same key
        String first = dispatchBody(delivery);
        String retry = dispatchBody(delivery);

        // THEN the first turn surfaces the sanitized error event and the retry is reprocessed
        assertThat(first).contains("event:error").contains("ERR_UPSTREAM");
        assertThat(retry).contains("event:chunk").contains(ANSWER).contains("event:done");
        assertThat(retry).doesNotContain(LISTEN_PROMPT);
        assertThat(flaky().calls()).isEqualTo(2);
    }

    @Test
    void a_successful_stream_still_dedupes_a_re_delivery_with_the_same_key() throws Exception {
        // GIVEN a first streamed turn that succeeds and keeps its reservation
        String delivery = delivery("idem-happy");
        String first = dispatchBody(delivery);
        assertThat(first).contains("event:done").contains(ANSWER);

        // WHEN the same delivery is streamed again
        String second = dispatchBody(delivery);

        // THEN the duplicate short-circuits to a safe listen prompt without reopening the stream
        assertThat(second).contains(LISTEN_PROMPT);
        assertThat(flaky().calls()).isEqualTo(1);
    }

    private FlakyStreamUseCase flaky() {
        return (FlakyStreamUseCase) converseStreamUseCase;
    }

    private String delivery(String idempotencyKey) {
        return "{\"transcript\":\"Bonjour\",\"channel\":\"genesys\","
                + "\"external_session_id\":\"genesys-conv-9\",\"idempotency_key\":\"" + idempotencyKey + "\"}";
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

    @TestConfiguration
    static class Config {
        @Bean
        ConverseStreamUseCase converseStreamUseCase() {
            return new FlakyStreamUseCase();
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

    // Fails the next N times it is asked to open a stream, then succeeds with a distinctive answer.
    // `calls()` proves whether a re-delivery reopened the stream (retry reprocessed) or was
    // short-circuited (duplicate). Failure/success are set per test so methods stay independent.
    static final class FlakyStreamUseCase implements ConverseStreamUseCase {
        private final AtomicInteger streamCalls = new AtomicInteger();
        private final AtomicInteger failuresRemaining = new AtomicInteger();

        void reset() {
            streamCalls.set(0);
            failuresRemaining.set(0);
        }

        void failNext(int times) {
            failuresRemaining.set(times);
        }

        int calls() {
            return streamCalls.get();
        }

        @Override
        public TokenStream converseStream(String transcript, String conversationId) {
            return converseStream(transcript, conversationId, null);
        }

        @Override
        public TokenStream converseStream(String transcript, String conversationId, String forcedLanguage) {
            streamCalls.incrementAndGet();
            if (failuresRemaining.getAndUpdate(n -> n > 0 ? n - 1 : 0) > 0) {
                throw new UpstreamUnavailableException("upstream 503");
            }
            return onChunk -> {
                onChunk.accept(ANSWER);
                return GeneratedAnswer.grounded(ANSWER, 0.83);
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
