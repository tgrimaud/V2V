package com.voicesupport.knowledge.domain.port.out;

// Observability hook for query-time retrieval re-ranking (TASK-BE-028). The domain reports that
// MMR ran and its candidate-in/selected-out counts; the infra adapter turns it into Micrometer
// metrics + a [RETRIEVAL-MMR] structured log. Kept as a domain out-port so the retrieval service
// stays pure and testable with a fake (no Micrometer/SLF4J), mirroring SyncObserverPort.
public interface RetrievalObserverPort {

    // MMR selected `selectedCount` chunks out of `candidateCount` over-fetched (`fetchK` requested)
    // for the given normalized domain (null = no restriction), at the configured lambda.
    void mmrApplied(String domain, int fetchK, int candidateCount, int selectedCount, double lambda);

    // No-op used when MMR is disabled or in tests that do not assert observability.
    RetrievalObserverPort NOOP = (domain, fetchK, candidateCount, selectedCount, lambda) -> {
    };
}
