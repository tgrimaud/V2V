package com.voicesupport.conversation.domain.port.out;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.util.List;

// Outbound port for the LLM wording step: turns grounded evidence into a concise, spoken answer
// in the language decided for the turn (TASK-BE-015). Implemented by provider adapters (Mistral,
// Ollama, ...) selected by configuration; the domain stays agnostic to the LLM SDK (DEC-011).
public interface AnswerGeneratorPort {

    String generate(String question, List<RetrievedEvidence> evidence, List<String> history, AnswerLanguage language);
}
