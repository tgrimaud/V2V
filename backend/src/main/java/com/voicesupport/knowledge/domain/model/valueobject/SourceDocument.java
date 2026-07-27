package com.voicesupport.knowledge.domain.model.valueobject;

import java.time.Instant;

public record SourceDocument(
        String sourceType,
        String sourceId,
        String title,
        String url,
        String content,
        String domain,
        String audience,
        String language,
        Instant updatedAt,
        String contentHash
) {

    public static final String DEFAULT_AUDIENCE = "customer";

    // ADR-0034: callers with no audience signal (markdown KB, one-shot ingest, tests) default to
    // the customer audience, so the fail-closed retrieval filter keeps serving them after re-sync.
    public static SourceDocument create(
            String sourceType,
            String sourceId,
            String title,
            String url,
            String content,
            String domain,
            String language,
            Instant updatedAt) {
        return create(sourceType, sourceId, title, url, content, domain, DEFAULT_AUDIENCE, language, updatedAt);
    }

    public static SourceDocument create(
            String sourceType,
            String sourceId,
            String title,
            String url,
            String content,
            String domain,
            String audience,
            String language,
            Instant updatedAt) {
        return new SourceDocument(
                sourceType, sourceId, title, url, content,
                domain != null ? domain : "general",
                audience != null && !audience.isBlank() ? audience : DEFAULT_AUDIENCE,
                language,
                updatedAt,
                ContentHash.sha256(content));
    }
}
