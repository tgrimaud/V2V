package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;

public interface GroundQueryUseCase {

    // Runs the pre-LLM grounding pipeline: input guardrail, then domain-filtered
    // retrieval, then a post-retrieval confidence guardrail. Returns either grounded
    // evidence or a blocking guardrail decision (no LLM step happens here).
    GroundingResult ground(String question, String domain, int topK, boolean alreadyGreeted);
}
