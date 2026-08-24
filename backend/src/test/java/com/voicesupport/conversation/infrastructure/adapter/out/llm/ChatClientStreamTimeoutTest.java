package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.chat.prompt.Prompt;
import reactor.core.publisher.Flux;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

// TASK-BE-025: the streaming generate() path must fail fast when the provider stalls, instead of
// tying up the SSE worker until the 60 s emitter timeout. Drives the REAL adapter over a fake
// ChatModel whose stream() hangs, and asserts a bounded UpstreamUnavailableException + a `timeout`
// telemetry outcome (never polluting the success p95).
@DisplayName("AbstractChatClientAnswerAdapter streaming timeout (TASK-BE-025)")
class ChatClientStreamTimeoutTest {

    private static final long STREAM_TIMEOUT_MS = 100;
    private static final List<RetrievedEvidence> EVIDENCE =
            List.of(new RetrievedEvidence("ctx", "s", "d", 0.9));

    private static ChatResponse token(String text) {
        return new ChatResponse(List.of(new Generation(new AssistantMessage(text))));
    }

    private MistralAnswerAdapter adapterOver(ChatModel model, SimpleMeterRegistry registry) {
        return new MistralAnswerAdapter(
                ChatClient.builder(model).build(), new BackendTelemetry(registry), 0, STREAM_TIMEOUT_MS, 0);
    }

    @Test
    @DisplayName("a stream that never emits aborts within the budget as a timeout outcome")
    void hungStreamAbortsWithinBudgetAsTimeout() {
        // GIVEN a provider whose stream never produces a token
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MistralAnswerAdapter adapter = adapterOver(new HangingChatModel(Flux.never()), registry);
        List<String> forwarded = new ArrayList<>();

        // WHEN the streaming answer is requested
        long start = System.nanoTime();
        assertThrows(UpstreamUnavailableException.class, () ->
                adapter.generate("q", EVIDENCE, List.of(), AnswerLanguage.ENGLISH, forwarded::add));
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        // THEN it fails fast (well under the 60 s emitter timeout), forwards nothing, and records timeout
        assertTrue(elapsedMs < 5_000, "expected fail-fast within budget, took " + elapsedMs + " ms");
        assertTrue(forwarded.isEmpty(), "no token should be forwarded on a hung stream");
        assertEquals(1, timeoutCount(registry), "the llm_wording slice should record a timeout outcome");
    }

    @Test
    @DisplayName("a stream that stalls after the first token aborts as a timeout outcome")
    void firstTokenThenStallAbortsAsTimeout() {
        // GIVEN a provider that emits one token then never emits again
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MistralAnswerAdapter adapter =
                adapterOver(new HangingChatModel(Flux.just(token("Bonjour")).concatWith(Flux.never())), registry);
        List<String> forwarded = new ArrayList<>();

        // WHEN the streaming answer is requested
        assertThrows(UpstreamUnavailableException.class, () ->
                adapter.generate("q", EVIDENCE, List.of(), AnswerLanguage.ENGLISH, forwarded::add));

        // THEN the first token reached the consumer, but the inter-token stall is a timeout
        assertEquals(List.of("Bonjour"), forwarded);
        assertEquals(1, timeoutCount(registry), "an inter-token stall should record a timeout outcome");
    }

    @Test
    @DisplayName("a stream that completes within budget is forwarded normally (no false timeout)")
    void completedStreamSucceeds() {
        // GIVEN a provider that emits two tokens and completes
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MistralAnswerAdapter adapter =
                adapterOver(new HangingChatModel(Flux.just(token("Hello "), token("world"))), registry);
        List<String> forwarded = new ArrayList<>();

        // WHEN the streaming answer is requested
        adapter.generate("q", EVIDENCE, List.of(), AnswerLanguage.ENGLISH, forwarded::add);

        // THEN both tokens are forwarded and no timeout is recorded
        assertEquals(List.of("Hello ", "world"), forwarded);
        assertEquals(0, timeoutCount(registry), "a completed stream must not record a timeout");
    }

    private static long timeoutCount(SimpleMeterRegistry registry) {
        return registry.find("voice_support.slice")
                .tag("slice", Slices.LLM_WORDING)
                .tag("outcome", "timeout")
                .timers().stream()
                .mapToLong(t -> t.count())
                .sum();
    }

    // Fake ChatModel that returns a caller-supplied stream, so a hung/partial/complete Flux can be
    // injected. call() is unused on the streaming path.
    private static final class HangingChatModel implements ChatModel {
        private final Flux<ChatResponse> stream;

        private HangingChatModel(Flux<ChatResponse> stream) {
            this.stream = stream;
        }

        @Override
        public ChatResponse call(Prompt prompt) {
            return token("");
        }

        @Override
        public Flux<ChatResponse> stream(Prompt prompt) {
            return stream;
        }
    }
}
