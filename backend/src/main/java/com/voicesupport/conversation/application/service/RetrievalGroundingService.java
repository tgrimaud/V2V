package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.conversation.domain.service.EvidenceContextTrimmer;
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
    // Prefill-reduction context budget (TASK-BE-033 lever 2). Applied AFTER the confidence guardrail
    // (which scores the raw retrieval), so answerable/confidence is unaffected; only the text handed
    // to the LLM + OutputGuardrail is capped. Disabled by default => behaviour unchanged.
    private final EvidenceContextTrimmer contextTrimmer;

    // Backward-compatible constructor: no context trimming (used by tests/fixtures).
    public RetrievalGroundingService(
            InputGuardrail inputGuardrail,
            RetrievalConfidenceGuardrail confidenceGuardrail,
            KnowledgeRetrievalPort knowledgeRetrievalPort) {
        this(inputGuardrail, confidenceGuardrail, knowledgeRetrievalPort, EvidenceContextTrimmer.disabled());
    }

    public RetrievalGroundingService(
            InputGuardrail inputGuardrail,
            RetrievalConfidenceGuardrail confidenceGuardrail,
            KnowledgeRetrievalPort knowledgeRetrievalPort,
            EvidenceContextTrimmer contextTrimmer) {
        this.inputGuardrail = inputGuardrail;
        this.confidenceGuardrail = confidenceGuardrail;
        this.knowledgeRetrievalPort = knowledgeRetrievalPort;
        this.contextTrimmer = contextTrimmer;
    }

    @Override
    public GroundingResult ground(String question, String domain, int topK, boolean alreadyGreeted,
            AnswerLanguage language) {
        GuardrailDecision inputDecision = inputGuardrail.check(question, alreadyGreeted, language);
        if (inputDecision.blocked()) {
            return GroundingResult.blocked(inputDecision);
        }
        // TASK-BE-034 (ADR-0048): scope retrieval to the turn's answer language (fr/en) so a
        // bilingual store returns same-language + untagged chunks only. The filter is a no-op when
        // disabled or on a single-corpus deployment; language is orthogonal to the domain axis.
        List<RetrievedEvidence> evidence =
                knowledgeRetrievalPort.retrieve(question, domain, language.code(), topK);
        GuardrailDecision confidenceDecision = confidenceGuardrail.check(evidence, language);
        if (confidenceDecision.blocked()) {
            return GroundingResult.blocked(confidenceDecision);
        }
        return GroundingResult.answerable(contextTrimmer.trim(evidence));
    }
}
