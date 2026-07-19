package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;

public interface AnswerQuestionUseCase {

    // Produces the spoken answer text (TASK-BE-005): runs the pre-LLM grounding pipeline,
    // then, when answerable, the LLM wording step and the output guardrail (DEC-002).
    // Blocked or ungrounded cases return a safe fallback, never an invented answer.
    // Conversation memory and the ADR-0021 HTTP contract are TASK-BE-006.
    GeneratedAnswer answer(String question, String domain, int topK, boolean alreadyGreeted);
}
