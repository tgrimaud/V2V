package com.voicesupport.domain.model;

import java.time.Instant;

public record SourceDocument(
        String sourceType,
        String sourceId,
        String title,
        String url,
        String content,
        String domain,
        String language,
        Instant updatedAt,
        String contentHash
) {

    public static SourceDocument create(
            String sourceType,
            String sourceId,
            String title,
            String url,
            String content,
            String domain,
            String language,
            Instant updatedAt) {
        return new SourceDocument(
                sourceType, sourceId, title, url, content,
                domain != null ? domain : "general",
                language,
                updatedAt,
                ContentHash.sha256(content));
    }
}
