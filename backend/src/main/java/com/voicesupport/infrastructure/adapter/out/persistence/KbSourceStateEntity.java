package com.voicesupport.infrastructure.adapter.out.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

import java.time.Instant;

@Entity
@Table(name = "kb_source_state")
@IdClass(KbSourceStateId.class)
public class KbSourceStateEntity {

    @Id
    @Column(name = "source_type", nullable = false)
    private String sourceType;

    @Id
    @Column(name = "source_id", nullable = false)
    private String sourceId;

    @Column(name = "content_hash", nullable = false)
    private String contentHash;

    @Column(name = "updated_at")
    private Instant updatedAt;

    @Column(name = "chunk_count", nullable = false)
    private int chunkCount;

    protected KbSourceStateEntity() {
    }

    public KbSourceStateEntity(String sourceType, String sourceId, String contentHash, Instant updatedAt, int chunkCount) {
        this.sourceType = sourceType;
        this.sourceId = sourceId;
        this.contentHash = contentHash;
        this.updatedAt = updatedAt;
        this.chunkCount = chunkCount;
    }

    public String getSourceType() {
        return sourceType;
    }

    public String getSourceId() {
        return sourceId;
    }

    public String getContentHash() {
        return contentHash;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public int getChunkCount() {
        return chunkCount;
    }

    public void update(String contentHash, Instant updatedAt, int chunkCount) {
        this.contentHash = contentHash;
        this.updatedAt = updatedAt;
        this.chunkCount = chunkCount;
    }
}
