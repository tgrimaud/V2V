package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.model.valueobject.WarmUpResult;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.conversation.domain.port.out.StreamingAnswerGeneratorPort;
import com.voicesupport.conversation.fake.FakeAnswerGeneratorPort;
import com.voicesupport.conversation.fake.FakeKnowledgeRetrievalPort;
import com.voicesupport.conversation.fake.FakeStreamingAnswerGeneratorPort;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("WarmUpService (connect-time embedding + LLM + streaming warm-up, side-effect-free, non-blocking)")
class WarmUpServiceTest {

    private static final String WARM_QUERY = "hello";

    private FakeKnowledgeRetrievalPort retrieval;
    private FakeAnswerGeneratorPort generator;
    private FakeStreamingAnswerGeneratorPort streamingGenerator;
    private SimpleMeterRegistry meterRegistry;
    private WarmUpService service;

    @BeforeEach
    void setUp() {
        retrieval = new FakeKnowledgeRetrievalPort();
        generator = new FakeAnswerGeneratorPort();
        streamingGenerator = new FakeStreamingAnswerGeneratorPort();
        meterRegistry = new SimpleMeterRegistry();
        service = new WarmUpService(retrieval, generator, streamingGenerator, new BackendTelemetry(meterRegistry),
                WARM_QUERY, AnswerLanguage.ENGLISH);
    }

    @Test
    @DisplayName("warms the embedding, the synchronous LLM and the streaming path once when all succeed")
    void warms_embedding_llm_and_stream() {
        // GIVEN a knowledge base that returns one chunk for the warm query
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));
        streamingGenerator.setNextTokens(List.of("Warm. "));

        // WHEN the models are warmed
        WarmUpResult result = service.warmUp();

        // THEN all three are marked warmed and each port was exercised exactly once with the warm query
        assertTrue(result.fullyWarmed());
        assertTrue(result.streamWarmed());
        assertEquals(1, retrieval.callCount);
        assertEquals(1, generator.callCount);
        assertEquals(1, streamingGenerator.callCount);
        assertEquals(AnswerLanguage.ENGLISH, streamingGenerator.lastLanguage);
    }

    @Test
    @DisplayName("feeds no conversation history to the streaming LLM (touches no memory)")
    void streaming_warm_touches_no_memory() {
        // GIVEN evidence for the warm query
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));

        // WHEN warmed twice
        service.warmUp();
        service.warmUp();

        // THEN the streaming LLM never receives prior-turn history and stays warm on repeat calls
        assertTrue(streamingGenerator.lastHistory.isEmpty());
        assertEquals(2, streamingGenerator.callCount);
    }

    @Test
    @DisplayName("a failing streaming warm-up is non-blocking: warm-up returns a miss and records it")
    void streaming_failure_is_non_blocking() {
        // GIVEN a healthy embedding + sync LLM but a streaming generator that throws (cold reactive path)
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));
        service = new WarmUpService(retrieval, generator, throwingStreamingGenerator(),
                new BackendTelemetry(meterRegistry), WARM_QUERY, AnswerLanguage.ENGLISH);

        // WHEN warmed
        WarmUpResult result = service.warmUp();

        // THEN embedding + LLM warmed, the streaming path is a miss, no exception escaped, miss recorded
        assertTrue(result.embeddingWarmed());
        assertTrue(result.llmWarmed());
        assertFalse(result.streamWarmed());
        assertFalse(result.fullyWarmed());
        assertEquals(1.0, sliceCount("warmup_stream", "error"));
    }

    @Test
    @DisplayName("a disabled streaming warm-up (null generator) is skipped and reported warmed, no slice")
    void streaming_disabled_is_skipped() {
        // GIVEN streaming warm-up disabled (no streaming generator wired)
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));
        service = new WarmUpService(retrieval, generator, null, new BackendTelemetry(meterRegistry),
                WARM_QUERY, AnswerLanguage.ENGLISH);

        // WHEN warmed
        WarmUpResult result = service.warmUp();

        // THEN the streaming path is reported warmed (nothing left cold by us) and no streaming slice is timed
        assertTrue(result.streamWarmed());
        assertTrue(result.fullyWarmed());
        assertThrows(io.micrometer.core.instrument.search.MeterNotFoundException.class,
                () -> sliceCount("warmup_stream", "success"));
    }

    @Test
    @DisplayName("records a success timing for each warmed model, streaming included")
    void records_success_slices() {
        // GIVEN a healthy stack
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));

        // WHEN warmed
        service.warmUp();

        // THEN all three warm-up slices are timed with a success outcome
        assertEquals(1.0, sliceCount("warmup_embedding", "success"));
        assertEquals(1.0, sliceCount("warmup_llm", "success"));
        assertEquals(1.0, sliceCount("warmup_stream", "success"));
    }

    @Test
    @DisplayName("a failing embedding is non-blocking: the LLM + streaming path are still warmed with empty evidence")
    void embedding_failure_is_non_blocking() {
        // GIVEN a retrieval port that throws (cold vector store)
        service = new WarmUpService(throwingRetrieval(), generator, streamingGenerator,
                new BackendTelemetry(meterRegistry), WARM_QUERY, AnswerLanguage.ENGLISH);

        // WHEN warmed
        WarmUpResult result = service.warmUp();

        // THEN embedding is a miss, the LLM + streaming path were still warmed on empty evidence
        assertFalse(result.embeddingWarmed());
        assertTrue(result.llmWarmed());
        assertTrue(result.streamWarmed());
        assertTrue(generator.lastEvidence.isEmpty());
        assertTrue(streamingGenerator.lastEvidence.isEmpty());
        assertEquals(1.0, sliceCount("warmup_embedding", "error"));
    }

    @Test
    @DisplayName("a failing sync LLM is non-blocking: the streaming path is still warmed and the miss recorded")
    void sync_llm_failure_is_non_blocking() {
        // GIVEN a healthy retrieval but a sync LLM that throws
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));
        service = new WarmUpService(retrieval, throwingGenerator(), streamingGenerator,
                new BackendTelemetry(meterRegistry), WARM_QUERY, AnswerLanguage.ENGLISH);

        // WHEN warmed
        WarmUpResult result = service.warmUp();

        // THEN embedding + streaming warmed, sync LLM is a miss, no exception escaped, the miss is recorded
        assertTrue(result.embeddingWarmed());
        assertFalse(result.llmWarmed());
        assertTrue(result.streamWarmed());
        assertFalse(result.fullyWarmed());
        assertEquals(1.0, sliceCount("warmup_llm", "error"));
    }

    private double sliceCount(String slice, String outcome) {
        return meterRegistry.get("voice_support.slice")
                .tag("slice", slice)
                .tag("provider", "warmup")
                .tag("outcome", outcome)
                .timer()
                .count();
    }

    private KnowledgeRetrievalPort throwingRetrieval() {
        return (query, domain, topK) -> {
            throw new IllegalStateException("vector store unavailable");
        };
    }

    private AnswerGeneratorPort throwingGenerator() {
        return (question, evidence, history, language) -> {
            throw new IllegalStateException("llm unavailable");
        };
    }

    private StreamingAnswerGeneratorPort throwingStreamingGenerator() {
        return (question, evidence, history, language, onToken) -> {
            throw new IllegalStateException("llm streaming unavailable");
        };
    }
}
