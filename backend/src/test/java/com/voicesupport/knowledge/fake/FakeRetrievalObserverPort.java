package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.port.out.RetrievalObserverPort;

public class FakeRetrievalObserverPort implements RetrievalObserverPort {

    public int calls;
    public String lastDomain;
    public int lastFetchK;
    public int lastCandidateCount;
    public int lastSelectedCount;
    public double lastLambda;

    @Override
    public void mmrApplied(String domain, int fetchK, int candidateCount, int selectedCount, double lambda) {
        this.calls++;
        this.lastDomain = domain;
        this.lastFetchK = fetchK;
        this.lastCandidateCount = candidateCount;
        this.lastSelectedCount = selectedCount;
        this.lastLambda = lambda;
    }
}
