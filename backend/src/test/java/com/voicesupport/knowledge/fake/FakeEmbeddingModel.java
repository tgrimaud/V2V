package com.voicesupport.knowledge.fake;

import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

// Deterministic embedding fake: the first keyword contained in the input text wins,
// otherwise a default vector is returned. No network, no Spring context.
public class FakeEmbeddingModel implements EmbeddingModel {

    private final Map<String, float[]> keywordVectors = new LinkedHashMap<>();
    private final List<String> failKeywords = new ArrayList<>();
    private float[] defaultVector = new float[]{0.0f, 0.0f, 0.0f};

    public FakeEmbeddingModel on(String keyword, float[] vector) {
        keywordVectors.put(keyword, vector);
        return this;
    }

    public FakeEmbeddingModel withDefault(float[] vector) {
        this.defaultVector = vector;
        return this;
    }

    public FakeEmbeddingModel failOn(String keyword) {
        failKeywords.add(keyword);
        return this;
    }

    @Override
    public float[] embed(String text) {
        for (String failKeyword : failKeywords) {
            if (text.contains(failKeyword)) {
                throw new IllegalStateException("embedding backend unavailable");
            }
        }
        for (Map.Entry<String, float[]> entry : keywordVectors.entrySet()) {
            if (text.contains(entry.getKey())) {
                return entry.getValue();
            }
        }
        return defaultVector;
    }

    @Override
    public float[] embed(Document document) {
        return embed(document.getText());
    }

    @Override
    public EmbeddingResponse call(EmbeddingRequest request) {
        throw new UnsupportedOperationException("not needed for tests");
    }
}
