package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.model.valueobject.WarmUpResult;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.conversation.fake.FakeAnswerGeneratorPort;
import com.voicesupport.conversation.fake.FakeKnowledgeRetrievalPort;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("WarmUpService (connect-time embedding + LLM warm-up, side-effect-free, non-blocking)")
class WarmUpServiceTest {

    private static final String WARM_QUERY = "hello";

    private FakeKnowledgeRetrievalPort retrieval;
    private FakeAnswerGeneratorPort generator;
    private SimpleMeterRegistry meterRegistry;
    private WarmUpService service;

    @BeforeEach
    void setUp() {
        retrieval = new FakeKnowledgeRetrievalPort();
        generator = new FakeAnswerGeneratorPort();
        meterRegistry = new SimpleMeterRegistry();
        service = new WarmUpService(retrieval, generator, new BackendTelemetry(meterRegistry),
                WARM_QUERY, AnswerLanguage.ENGLISH);
    }

    @Test
    @DisplayName("warms both the embedding (retrieval) and the LLM once when both succeed")
    void warms_embedding_and_llm() {
        // GIVEN a knowledge base that returns one chunk for the warm query
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));

        // WHEN the models are warmed
        WarmUpResult result = service.warmUp();

        // THEN both are marked warmed and each port was exercised exactly once with the warm query
        assertTrue(result.fullyWarmed());
        assertEquals(1, retrieval.callCount);
        assertEquals(WARM_QUERY, retrieval.lastQuery);
        assertEquals(1, retrieval.lastTopK);
        assertEquals(1, generator.callCount);
        assertEquals(WARM_QUERY, generator.lastQuestion);
        assertEquals(AnswerLanguage.ENGLISH, generator.lastLanguage);
    }

    @Test
    @DisplayName("feeds no conversation history to the LLM (touches no memory)")
    void touches_no_memory() {
        // GIVEN evidence for the warm query
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));

        // WHEN warmed twice
        service.warmUp();
        service.warmUp();

        // THEN the LLM never receives prior-turn history (no memory is involved) and it stays warm
        assertTrue(generator.lastHistory.isEmpty());
        assertEquals(2, generator.callCount);
        assertEquals(2, retrieval.callCount);
    }

    @Test
    @DisplayName("a failing embedding is non-blocking: the LLM is still warmed and the miss is recorded")
    void embedding_failure_is_non_blocking() {
        // GIVEN a retrieval port that throws (cold vector store)
        service = new WarmUpService(throwingRetrieval(), generator, new BackendTelemetry(meterRegistry),
                WARM_QUERY, AnswerLanguage.ENGLISH);

        // WHEN warmed
        WarmUpResult result = service.warmUp();

        // THEN embedding is a miss, the LLM was still warmed (empty evidence), and no exception escaped
        assertFalse(result.embeddingWarmed());
        assertTrue(result.llmWarmed());
        assertEquals(1, generator.callCount);
        assertTrue(generator.lastEvidence.isEmpty());
        assertEquals(1.0, sliceCount("warmup_embedding", "error"));
    }

    @Test
    @DisplayName("a failing LLM is non-blocking: warm-up returns a miss and the miss is recorded")
    void llm_failure_is_non_blocking() {
        // GIVEN a healthy retrieval but an LLM that throws
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));
        service = new WarmUpService(retrieval, throwingGenerator(), new BackendTelemetry(meterRegistry),
                WARM_QUERY, AnswerLanguage.ENGLISH);

        // WHEN warmed
        WarmUpResult result = service.warmUp();

        // THEN embedding warmed, LLM is a miss, no exception escaped, and the miss is recorded
        assertTrue(result.embeddingWarmed());
        assertFalse(result.llmWarmed());
        assertFalse(result.fullyWarmed());
        assertEquals(1.0, sliceCount("warmup_llm", "error"));
    }

    @Test
    @DisplayName("records a success timing for each warmed model")
    void records_success_slices() {
        // GIVEN a healthy stack
        retrieval.setEvidence(List.of(new RetrievedEvidence("ctx", "s1", "billing", 0.7)));

        // WHEN warmed
        service.warmUp();

        // THEN both warm-up slices are timed with a success outcome
        assertEquals(1.0, sliceCount("warmup_embedding", "success"));
        assertEquals(1.0, sliceCount("warmup_llm", "success"));
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
        return new AnswerGeneratorPort() {
            @Override
            public String generate(String question, List<RetrievedEvidence> evidence,
                    List<String> history, AnswerLanguage language) {
                throw new IllegalStateException("llm unavailable");
            }
        };
    }
}
