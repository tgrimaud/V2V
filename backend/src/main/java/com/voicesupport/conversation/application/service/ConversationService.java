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
// history), then records the completed turn. Retrieval spans all domains (V1 has no
// domain classifier here); the answer stays grounded and DEC-002-safe by construction.
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
