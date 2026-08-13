package com.voicesupport.knowledge.domain.port.out;

// Observability hook for query-time retrieval shaping (TASK-BE-028 MMR, TASK-BE-029 query
// normalization). The domain reports what it did; the infra adapter turns it into Micrometer
// metrics + structured logs. Kept as a domain out-port so the retrieval service stays pure and
// testable with a fake (no Micrometer/SLF4J), mirroring SyncObserverPort.
public interface RetrievalObserverPort {

    // MMR selected `selectedCount` chunks out of `candidateCount` over-fetched (`fetchK` requested)
    // for the given normalized domain (null = no restriction), at the configured lambda.
    void mmrApplied(String domain, int fetchK, int candidateCount, int selectedCount, double lambda);

    // TASK-BE-029: a leading greeting was stripped from the embedding query for `domain`
    // (null = no restriction). Lengths (not content) are reported to avoid logging the raw query.
    void queryNormalized(String domain, int originalLength, int normalizedLength);
}
