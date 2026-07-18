package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceStatePort;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class FakeKnowledgeSourceStatePort implements KnowledgeSourceStatePort {

    private final Map<String, String> hashes = new LinkedHashMap<>();

    private static String key(String sourceType, String sourceId) {
        return sourceType + "\u0000" + sourceId;
    }

    @Override
    public Optional<String> findHash(String sourceType, String sourceId) {
        return Optional.ofNullable(hashes.get(key(sourceType, sourceId)));
    }

    @Override
    public void upsertState(String sourceType, String sourceId, String contentHash, Instant updatedAt, int chunkCount) {
        hashes.put(key(sourceType, sourceId), contentHash);
    }

    @Override
    public List<String> listSourceIds(String sourceType) {
        List<String> ids = new ArrayList<>();
        String prefix = sourceType + "\u0000";
        for (String k : hashes.keySet()) {
            if (k.startsWith(prefix)) {
                ids.add(k.substring(prefix.length()));
            }
        }
        return ids;
    }

    @Override
    public void deleteState(String sourceType, String sourceId) {
        hashes.remove(key(sourceType, sourceId));
    }
}
