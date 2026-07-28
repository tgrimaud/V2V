package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import io.swagger.v3.oas.annotations.media.Schema;

import java.util.List;

@Schema(description = "Grounding decision plus the grounded evidence used to reach it.")
public record RetrievalResponse(
        @Schema(description = "Whether the query can be answered from grounded evidence.") boolean answerable,
        @Schema(description = "Guardrail verdict name.", example = "ANSWERABLE") String verdict,
        @Schema(description = "Safe fallback message when not answerable; null otherwise.") String fallbackMessage,
        @Schema(description = "Grounded evidence chunks.") List<EvidenceView> evidence) {

    @Schema(description = "A single grounded evidence chunk.")
    public record EvidenceView(
            @Schema(description = "Chunk text.") String text,
            @Schema(description = "Source id of the chunk.") String sourceId,
            @Schema(description = "Domain tag of the chunk.") String domain,
            @Schema(description = "Similarity score.", example = "0.74") double score) {

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
