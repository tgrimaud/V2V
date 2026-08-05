package com.voicesupport.conversation.infrastructure.adapter.out.knowledge;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.fake.FakeKnowledgeRetrievalUseCase;
import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("InProc knowledge retrieval seam (ACL)")
class InProcKnowledgeRetrievalAdapterTest {

    // Disabled retrieval budget for the mapping tests (they run synchronously, no timeout concern).
    private static final long NO_BUDGET = 0;
    private static final long SHORT_BUDGET_MS = 100;

    private final BackendTelemetry telemetry = new BackendTelemetry(new SimpleMeterRegistry());

    @Test
    @DisplayName("maps knowledge chunks to conversation evidence through the ACL")
    void mapsChunksToEvidence() {
        // GIVEN a knowledge use case returning two chunks
        var fake = new FakeKnowledgeRetrievalUseCase();
        fake.setChunks(List.of(
                new KnowledgeChunk("proration explained", "billing-faq#1", "billing", 0.82),
                new KnowledgeChunk("late fee explained", "billing-faq#2", "billing", 0.71)));
        var adapter = new InProcKnowledgeRetrievalAdapter(fake, telemetry, NO_BUDGET);

        // WHEN the conversation context retrieves through the seam
        List<RetrievedEvidence> evidence = adapter.retrieve("why is my bill higher", "billing", 5);

        // THEN chunks are translated into the conversation domain model
        assertEquals(2, evidence.size());
        assertEquals("proration explained", evidence.get(0).text());
        assertEquals("billing-faq#1", evidence.get(0).sourceId());
        assertEquals("billing", evidence.get(0).domain());
        assertEquals(0.82, evidence.get(0).score());
    }

    @Test
    @DisplayName("honors the requested top-k limit")
    void honorsTopK() {
        // GIVEN three available chunks
        var fake = new FakeKnowledgeRetrievalUseCase();
        fake.setChunks(List.of(
                new KnowledgeChunk("a", "s1", "general", 0.9),
                new KnowledgeChunk("b", "s2", "general", 0.8),
                new KnowledgeChunk("c", "s3", "general", 0.7)));
        var adapter = new InProcKnowledgeRetrievalAdapter(fake, telemetry, NO_BUDGET);

        // WHEN retrieving with topK = 2
        List<RetrievedEvidence> evidence = adapter.retrieve("q", "general", 2);

        // THEN only two evidence items are returned
        assertEquals(2, evidence.size());
    }

    @Test
    @DisplayName("a slow vector query fails fast within the budget as a timeout outcome (TASK-BE-025)")
    void slowRetrievalAbortsWithinBudgetAsTimeout() {
        // GIVEN a retrieval that stalls well past the configured budget (a locked/slow pgvector query)
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        BackendTelemetry meteredTelemetry = new BackendTelemetry(registry);
        KnowledgeRetrievalUseCase slow = (query, domain, topK) -> {
            try {
                Thread.sleep(5_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            return List.of();
        };
        var adapter = new InProcKnowledgeRetrievalAdapter(slow, meteredTelemetry, SHORT_BUDGET_MS);

        // WHEN the seam retrieves
        long start = System.nanoTime();
        assertThrows(UpstreamUnavailableException.class, () -> adapter.retrieve("q", null, 5));
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        // THEN it fails fast (well under the stall), freeing the worker, and records a timeout outcome
        // on the retrieval slice (never polluting the success p95).
        assertTrue(elapsedMs < 3_000, "expected fail-fast within budget, took " + elapsedMs + " ms");
        assertEquals(1, outcomeCount(registry, "timeout"), "retrieval slice should record a timeout outcome");
        assertEquals(0, outcomeCount(registry, "success"), "a timed-out retrieval must not record success");
    }

    @Test
    @DisplayName("a retrieval within budget records success (no false timeout)")
    void fastRetrievalRecordsSuccess() {
        // GIVEN a fast retrieval and a bounded budget
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        BackendTelemetry meteredTelemetry = new BackendTelemetry(registry);
        var fake = new FakeKnowledgeRetrievalUseCase();
        fake.setChunks(List.of(new KnowledgeChunk("a", "s1", "general", 0.9)));
        var adapter = new InProcKnowledgeRetrievalAdapter(fake, meteredTelemetry, SHORT_BUDGET_MS);

        // WHEN retrieving
        List<RetrievedEvidence> evidence = adapter.retrieve("q", "general", 5);

        // THEN it succeeds and records a success outcome, no timeout
        assertEquals(1, evidence.size());
        assertEquals(1, outcomeCount(registry, "success"));
        assertEquals(0, outcomeCount(registry, "timeout"));
    }

    private static long outcomeCount(SimpleMeterRegistry registry, String outcome) {
        return registry.find("voice_support.slice")
                .tag("slice", Slices.RETRIEVAL)
                .tag("outcome", outcome)
                .timers().stream()
                .mapToLong(Timer::count)
                .sum();
    }
}
