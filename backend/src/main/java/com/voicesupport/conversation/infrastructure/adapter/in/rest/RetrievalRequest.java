package com.voicesupport.conversation.infrastructure.adapter.in.rest;

public record RetrievalRequest(String question, String domain, Integer topK, Boolean alreadyGreeted) {

    private static final int DEFAULT_TOP_K = 4;

    public int effectiveTopK() {
        return topK != null && topK > 0 ? topK : DEFAULT_TOP_K;
    }

    public boolean effectiveAlreadyGreeted() {
        return Boolean.TRUE.equals(alreadyGreeted);
    }
}
