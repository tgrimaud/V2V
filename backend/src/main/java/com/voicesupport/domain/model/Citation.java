package com.voicesupport.domain.model;

public record Citation(
        String source,
        String section,
        String relevantText,
        double score
) {}
