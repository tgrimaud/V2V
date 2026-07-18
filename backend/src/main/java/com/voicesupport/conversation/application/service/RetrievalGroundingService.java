package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.conversation.domain.service.InputGuardrail;
import com.voicesupport.conversation.domain.service.RetrievalConfidenceGuardrail;

import java.util.List;

// Composes the pre-LLM grounding pipeline (ADR-0014): the input guardrail short-circuits
// off-topic / unsafe / greeting inputs before any retrieval, and the post-retrieval
// confidence guardrail blocks weakly-grounded answers. Retrieval reaches the knowledge
// context only through the outbound seam port.
public class RetrievalGroundingService implements GroundQueryUseCase {

    private final InputGuardrail inputGuardrail;
    private final RetrievalConfidenceGuardrail confidenceGuardrail;
    private final KnowledgeRetrievalPort knowledgeRetrievalPort;

    public RetrievalGroundingService(
            InputGuardrail inputGuardrail,
            RetrievalConfidenceGuardrail confidenceGuardrail,
            KnowledgeRetrievalPort knowledgeRetrievalPort) {
        this.inputGuardrail = inputGuardrail;
        this.confidenceGuardrail = confidenceGuardrail;
        this.knowledgeRetrievalPort = knowledgeRetrievalPort;
    }

    @Override
    public GroundingResult ground(String question, String domain, int topK, boolean alreadyGreeted) {
        GuardrailDecision inputDecision = inputGuardrail.check(question, alreadyGreeted);
        if (inputDecision.blocked()) {
            return GroundingResult.blocked(inputDecision);
        }
        List<RetrievedEvidence> evidence = knowledgeRetrievalPort.retrieve(question, domain, topK);
        GuardrailDecision confidenceDecision = confidenceGuardrail.check(question, evidence);
        if (confidenceDecision.blocked()) {
            return GroundingResult.blocked(confidenceDecision);
        }
        return GroundingResult.answerable(evidence);
    }
}
