package com.voicesupport.conversation.infrastructure.adapter.out.knowledge;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import java.util.List;

public class InProcKnowledgeRetrievalAdapter implements KnowledgeRetrievalPort {

    private static final String PROVIDER = "pgvector";

    private final KnowledgeRetrievalUseCase knowledgeRetrieval;
    private final BackendTelemetry telemetry;

    public InProcKnowledgeRetrievalAdapter(KnowledgeRetrievalUseCase knowledgeRetrieval, BackendTelemetry telemetry) {
        this.knowledgeRetrieval = knowledgeRetrieval;
        this.telemetry = telemetry;
    }

    @Override
    public List<RetrievedEvidence> retrieve(String query, String domain, int topK) {
        return telemetry.time(Slices.RETRIEVAL, PROVIDER, () -> knowledgeRetrieval.retrieve(query, domain, topK).stream()
                .map(InProcKnowledgeRetrievalAdapter::toEvidence)
                .toList());
    }

    private static RetrievedEvidence toEvidence(KnowledgeChunk chunk) {
        return new RetrievedEvidence(chunk.text(), chunk.sourceId(), chunk.domain(), chunk.score());
    }
}
