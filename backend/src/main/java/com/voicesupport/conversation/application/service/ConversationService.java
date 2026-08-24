package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.AnswerQuestionUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.out.ConversationMemoryPort;
import com.voicesupport.conversation.domain.service.ConversationHistoryFormatter;

import java.util.List;

// Stateful conversation orchestration (TASK-BE-006): loads the prior turns for a
// conversation, runs the BE-005 answer pipeline with that history placed in the system
// message (current turn excluded — avoids the greeting/duplication bugs in project
// history), then records the completed turn.
//
// BUG-007: retrieval is passed a null domain ON PURPOSE, so the voice/text path searches
// ALL domains (billing|support|commercial|general). This is the correct behaviour for the
// current single-pipeline product: there is no runtime classifier of the incoming QUESTION
// here (ADR-0015 multi-agent routing is NOT implemented on this branch). Note the
// DomainClassifierPort (ADR-0030) tags KB articles by domain at INGESTION time — it does not
// classify the runtime query — so no reliable per-question domain can be supplied; forcing one
// would need a query router and could DROP relevant chunks on a misclassification. Per-domain
// scoping stays available on /answer and /retrieve where the caller provides the domain. The
// audience fail-closed filter (ADR-0034, customer-only) and grounding/confidence guardrails
// still apply, so the answer stays DEC-002-safe by construction. The retrieval-precision
// trade-off of cross-domain search is tracked in OQ-008. Revisit only if/when a runtime query
// classifier is introduced.
public class ConversationService implements ConverseUseCase {

    private final AnswerQuestionUseCase answerQuestionUseCase;
    private final ConversationMemoryPort memory;
    // Retrieval top-K for the voice conversation path (TASK-BE-011): configurable so the RAG
    // context size (a driver of LLM time-to-first-token) can be tuned without a code change.
    private final int topK;

    public ConversationService(AnswerQuestionUseCase answerQuestionUseCase, ConversationMemoryPort memory, int topK) {
        this.answerQuestionUseCase = answerQuestionUseCase;
        this.memory = memory;
        this.topK = topK;
    }

    @Override
    public GeneratedAnswer converse(String transcript, String conversationId) {
        return converse(transcript, conversationId, null);
    }

    @Override
    public GeneratedAnswer converse(String transcript, String conversationId, String forcedLanguage) {
        List<ConversationTurn> priorTurns = memory.recentTurns(conversationId);
        boolean alreadyGreeted = !priorTurns.isEmpty();
        GeneratedAnswer answer = answerQuestionUseCase.answer(
                transcript, null, topK, alreadyGreeted,
                ConversationHistoryFormatter.format(priorTurns), forcedLanguage);
        memory.append(conversationId, new ConversationTurn(transcript, answer.text()));
        return answer;
    }
}
