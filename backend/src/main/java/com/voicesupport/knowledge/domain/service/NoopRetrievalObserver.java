package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.port.out.RetrievalObserverPort;

// No-op RetrievalObserverPort used when re-ranking/normalization are disabled or in tests that do
// not assert observability. Lives in the service package (not the port package) so the port stays a
// pure interface (ArchUnit: domain.port classes must be interfaces named *Port/*UseCase/*Connector).
final class NoopRetrievalObserver implements RetrievalObserverPort {

    static final NoopRetrievalObserver INSTANCE = new NoopRetrievalObserver();

    @Override
    public void mmrApplied(String domain, int fetchK, int candidateCount, int selectedCount, double lambda) {
    }

    @Override
    public void queryNormalized(String domain, int originalLength, int normalizedLength) {
    }
}
