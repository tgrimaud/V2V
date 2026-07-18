package com.voicesupport.knowledge.infrastructure.adapter.out.persistence;

import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceStatePort;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public class JpaKnowledgeSourceStateAdapter implements KnowledgeSourceStatePort {

    private final KbSourceStateRepository repository;

    public JpaKnowledgeSourceStateAdapter(KbSourceStateRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<String> findHash(String sourceType, String sourceId) {
        return repository.findById(new KbSourceStateId(sourceType, sourceId))
                .map(KbSourceStateEntity::getContentHash);
    }

    @Override
    public void upsertState(String sourceType, String sourceId, String contentHash, Instant updatedAt, int chunkCount) {
        KbSourceStateEntity entity = repository.findById(new KbSourceStateId(sourceType, sourceId))
                .map(existing -> {
                    existing.update(contentHash, updatedAt, chunkCount);
                    return existing;
                })
                .orElseGet(() -> new KbSourceStateEntity(sourceType, sourceId, contentHash, updatedAt, chunkCount));
        repository.save(entity);
    }

    @Override
    public List<String> listSourceIds(String sourceType) {
        return repository.findBySourceType(sourceType).stream()
                .map(KbSourceStateEntity::getSourceId)
                .toList();
    }

    @Override
    public void deleteState(String sourceType, String sourceId) {
        repository.deleteById(new KbSourceStateId(sourceType, sourceId));
    }
}
