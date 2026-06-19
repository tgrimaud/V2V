package com.voicesupport.domain.model;

public record KnowledgeChunk(
        String id,
        String content,
        String source,
        String section,
        int chunkIndex
) {}
