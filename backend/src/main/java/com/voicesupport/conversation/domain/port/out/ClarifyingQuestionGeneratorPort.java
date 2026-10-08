package com.voicesupport.conversation.domain.port.out;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;

import java.util.List;

// Outbound port for the US-043 / TASK-BE-071 bounded billing clarify turn: given the customer's
// under-specified billing turn and the prior conversation history, produce ONE short, natural
// clarifying question in the answer language (never an answer, never an amount — DEC-002). It is a
// separate port from AnswerGeneratorPort so the clarify-turn framing (ask, don't answer; no RAG
// context) stays explicit and the deterministic trigger/bound live in the orchestration layer.
public interface ClarifyingQuestionGeneratorPort {

    String generateClarifyingQuestion(String question, List<String> history, AnswerLanguage language);
}
