package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Question to answer via the retrieval + LLM wording pipeline.")
public record AnswerRequest(
        @Schema(description = "The question to answer.", example = "How do I change my plan?") String question,
        @Schema(description = "Optional domain filter (billing|support|commercial); null = any.") String domain,
        @Schema(description = "KB chunks to retrieve; defaults to 4 when null/<=0.", example = "4") Integer topK,
        @Schema(description = "Whether the assistant already greeted (suppresses a repeat greeting).")
        Boolean alreadyGreeted) {

    private static final int DEFAULT_TOP_K = 4;

    public int effectiveTopK() {
        return topK != null && topK > 0 ? topK : DEFAULT_TOP_K;
    }

    public boolean effectiveAlreadyGreeted() {
        return Boolean.TRUE.equals(alreadyGreeted);
    }
}
