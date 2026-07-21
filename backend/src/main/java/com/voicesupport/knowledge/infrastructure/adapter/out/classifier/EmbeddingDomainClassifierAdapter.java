package com.voicesupport.knowledge.infrastructure.adapter.out.classifier;

import com.voicesupport.knowledge.domain.port.out.DomainClassifierPort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.embedding.EmbeddingModel;

import java.util.LinkedHashMap;
import java.util.Map;

// ADR-0030: assigns a business domain to an otherwise-untagged source document by
// comparing its embedding (Ollama nomic-embed-text, 768d) against per-domain anchor
// vectors; below the similarity threshold the document stays "general". Anchor vectors
// are embedded once at construction. The same port is reused at query time by EPIC-011.
public class EmbeddingDomainClassifierAdapter implements DomainClassifierPort {

    public static final String GENERAL = "general";

    private static final Logger log = LoggerFactory.getLogger(EmbeddingDomainClassifierAdapter.class);

    private final EmbeddingModel embeddingModel;
    private final Map<String, float[]> anchorVectors;
    private final double threshold;
    private final int maxChars;

    public EmbeddingDomainClassifierAdapter(
            EmbeddingModel embeddingModel,
            Map<String, String> domainAnchors,
            double threshold,
            int maxChars) {
        this.embeddingModel = embeddingModel;
        this.threshold = threshold;
        this.maxChars = maxChars;
        this.anchorVectors = embedAnchors(domainAnchors);
    }

    @Override
    public String classify(String title, String content) {
        String text = classificationText(title, content);
        if (text.isBlank() || anchorVectors.isEmpty()) {
            return GENERAL;
        }
        // A transient embedding failure on one article must not abort a bulk sync of
        // thousands of rows; degrade that article to the safe "general" domain.
        try {
            return closestDomain(embeddingModel.embed(text));
        } catch (RuntimeException e) {
            log.warn("[KB-SYNC] domain classification failed, defaulting to general: {}", e.getMessage());
            return GENERAL;
        }
    }

    private String closestDomain(float[] vector) {
        String bestDomain = GENERAL;
        double bestScore = threshold;
        for (Map.Entry<String, float[]> anchor : anchorVectors.entrySet()) {
            double score = cosineSimilarity(vector, anchor.getValue());
            if (score >= bestScore) {
                bestScore = score;
                bestDomain = anchor.getKey();
            }
        }
        return bestDomain;
    }

    private Map<String, float[]> embedAnchors(Map<String, String> domainAnchors) {
        Map<String, float[]> vectors = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : domainAnchors.entrySet()) {
            vectors.put(entry.getKey(), embeddingModel.embed(entry.getValue()));
        }
        return vectors;
    }

    private String classificationText(String title, String content) {
        String safeTitle = title != null ? title : "";
        String safeContent = content != null ? content : "";
        String joined = (safeTitle + "\n" + safeContent).strip();
        return joined.length() > maxChars ? joined.substring(0, maxChars) : joined;
    }

    private double cosineSimilarity(float[] a, float[] b) {
        if (a.length != b.length) {
            return 0.0;
        }
        double dot = 0.0;
        double normA = 0.0;
        double normB = 0.0;
        for (int i = 0; i < a.length; i++) {
            dot += a[i] * b[i];
            normA += a[i] * a[i];
            normB += b[i] * b[i];
        }
        if (normA == 0.0 || normB == 0.0) {
            return 0.0;
        }
        return dot / (Math.sqrt(normA) * Math.sqrt(normB));
    }
}
