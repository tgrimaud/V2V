package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;

public interface GroundQueryUseCase {

    // Runs the pre-LLM grounding pipeline: input guardrail, then domain-filtered
    // retrieval, then a post-retrieval confidence guardrail. Returns either grounded
    // evidence or a blocking guardrail decision (no LLM step happens here). The answer
    // language is decided once per turn upstream so any blocking guardrail wording is
    // spoken in the language of the rest of the turn (session stickiness + default).
    GroundingResult ground(String question, String domain, int topK, boolean alreadyGreeted, AnswerLanguage language);
}
