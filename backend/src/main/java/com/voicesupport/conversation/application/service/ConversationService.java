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

    private static final int DEFAULT_TOP_K = 4;

    private final AnswerQuestionUseCase answerQuestionUseCase;
    private final ConversationMemoryPort memory;

    public ConversationService(AnswerQuestionUseCase answerQuestionUseCase, ConversationMemoryPort memory) {
        this.answerQuestionUseCase = answerQuestionUseCase;
        this.memory = memory;
    }

    @Override
    public GeneratedAnswer converse(String transcript, String conversationId) {
        List<ConversationTurn> priorTurns = memory.recentTurns(conversationId);
        boolean alreadyGreeted = !priorTurns.isEmpty();
        GeneratedAnswer answer = answerQuestionUseCase.answer(
                transcript, null, DEFAULT_TOP_K, alreadyGreeted, ConversationHistoryFormatter.format(priorTurns));
        memory.append(conversationId, new ConversationTurn(transcript, answer.text()));
        return answer;
    }
}
