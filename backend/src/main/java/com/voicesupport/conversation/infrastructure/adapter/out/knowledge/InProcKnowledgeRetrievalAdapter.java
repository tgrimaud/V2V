package com.voicesupport.conversation.infrastructure.adapter.out.knowledge;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import java.util.List;

public class InProcKnowledgeRetrievalAdapter implements KnowledgeRetrievalPort {

    private final KnowledgeRetrievalUseCase knowledgeRetrieval;

    public InProcKnowledgeRetrievalAdapter(KnowledgeRetrievalUseCase knowledgeRetrieval) {
        this.knowledgeRetrieval = knowledgeRetrieval;
    }

    @Override
    public List<RetrievedEvidence> retrieve(String query, String domain, int topK) {
        return knowledgeRetrieval.retrieve(query, domain, topK).stream()
                .map(InProcKnowledgeRetrievalAdapter::toEvidence)
                .toList();
    }

    private static RetrievedEvidence toEvidence(KnowledgeChunk chunk) {
        return new RetrievedEvidence(chunk.text(), chunk.sourceId(), chunk.domain(), chunk.score());
    }
}
