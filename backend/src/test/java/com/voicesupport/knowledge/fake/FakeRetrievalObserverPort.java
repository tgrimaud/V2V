package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.port.out.RetrievalObserverPort;

public class FakeRetrievalObserverPort implements RetrievalObserverPort {

    public int calls;
    public String lastDomain;
    public int lastFetchK;
    public int lastCandidateCount;
    public int lastSelectedCount;
    public double lastLambda;

    public int normalizeCalls;
    public String lastNormalizeDomain;
    public int lastOriginalLength;
    public int lastNormalizedLength;

    @Override
    public void mmrApplied(String domain, int fetchK, int candidateCount, int selectedCount, double lambda) {
        this.calls++;
        this.lastDomain = domain;
        this.lastFetchK = fetchK;
        this.lastCandidateCount = candidateCount;
        this.lastSelectedCount = selectedCount;
        this.lastLambda = lambda;
    }

    @Override
    public void queryNormalized(String domain, int originalLength, int normalizedLength) {
        this.normalizeCalls++;
        this.lastNormalizeDomain = domain;
        this.lastOriginalLength = originalLength;
        this.lastNormalizedLength = normalizedLength;
    }
}
