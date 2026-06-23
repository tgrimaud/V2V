package com.voicesupport.domain.port.out;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface KnowledgeSourceStatePort {

    Optional<String> findHash(String sourceType, String sourceId);

    void upsertState(String sourceType, String sourceId, String contentHash, Instant updatedAt, int chunkCount);

    List<String> listSourceIds(String sourceType);

    void deleteState(String sourceType, String sourceId);
}
