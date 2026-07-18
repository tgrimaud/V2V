package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.util.List;

public record RetrievalResponse(
        boolean answerable,
        String verdict,
        String fallbackMessage,
        List<EvidenceView> evidence) {

    public record EvidenceView(String text, String sourceId, String domain, double score) {

        static EvidenceView from(RetrievedEvidence evidence) {
            return new EvidenceView(evidence.text(), evidence.sourceId(), evidence.domain(), evidence.score());
        }
    }

    public static RetrievalResponse from(GroundingResult result) {
        List<EvidenceView> views = result.evidence().stream().map(EvidenceView::from).toList();
        return new RetrievalResponse(
                result.answerable(),
                result.decision().verdict().name(),
                result.decision().fallbackMessage(),
                views);
    }
}
