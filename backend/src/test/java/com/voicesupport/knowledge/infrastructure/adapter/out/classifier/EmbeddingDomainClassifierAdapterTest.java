package com.voicesupport.knowledge.infrastructure.adapter.out.classifier;

import com.voicesupport.knowledge.fake.FakeEmbeddingModel;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EmbeddingDomainClassifierAdapterTest {

    private static final Map<String, String> ANCHORS = Map.of(
            "billing", "BILLING_ANCHOR",
            "support", "SUPPORT_ANCHOR",
            "commercial", "COMMERCIAL_ANCHOR");

    private FakeEmbeddingModel embeddingModelWithOrthogonalAnchors() {
        return new FakeEmbeddingModel()
                .on("BILLING_ANCHOR", new float[]{1, 0, 0})
                .on("SUPPORT_ANCHOR", new float[]{0, 1, 0})
                .on("COMMERCIAL_ANCHOR", new float[]{0, 0, 1});
    }

    @Test
    void shouldClassifyToClosestDomainAboveThreshold() {
        // GIVEN an article whose embedding aligns with the billing anchor
        FakeEmbeddingModel model = embeddingModelWithOrthogonalAnchors()
                .on("invoice", new float[]{1, 0, 0});
        EmbeddingDomainClassifierAdapter classifier =
                new EmbeddingDomainClassifierAdapter(model, ANCHORS, 0.5, 2000);

        // WHEN classifying
        String domain = classifier.classify("My bill", "I have a question about my invoice");

        // THEN it resolves to the aligned domain
        assertEquals("billing", domain);
    }

    @Test
    void shouldFallBackToGeneralBelowThreshold() {
        // GIVEN an article whose embedding is only weakly related to every anchor (cosine ~0.707)
        FakeEmbeddingModel model = embeddingModelWithOrthogonalAnchors()
                .withDefault(new float[]{1, 1, 0});
        EmbeddingDomainClassifierAdapter classifier =
                new EmbeddingDomainClassifierAdapter(model, ANCHORS, 0.9, 2000);

        // WHEN classifying an off-topic article
        String domain = classifier.classify("Weather", "Something unrelated to any domain");

        // THEN it stays general because no anchor reaches the threshold
        assertEquals("general", domain);
    }

    @Test
    void shouldReturnGeneralForBlankContentWithoutEmbedding() {
        // GIVEN a classifier (anchors embedded once) and blank input
        EmbeddingDomainClassifierAdapter classifier =
                new EmbeddingDomainClassifierAdapter(embeddingModelWithOrthogonalAnchors(), ANCHORS, 0.5, 2000);

        // WHEN classifying blank title/content
        String domain = classifier.classify("  ", "");

        // THEN it short-circuits to general
        assertEquals("general", domain);
    }

    @Test
    void shouldReturnGeneralWhenNoAnchorsConfigured() {
        // GIVEN a classifier with no domain anchors
        EmbeddingDomainClassifierAdapter classifier =
                new EmbeddingDomainClassifierAdapter(new FakeEmbeddingModel(), Map.of(), 0.5, 2000);

        // WHEN classifying any content
        String domain = classifier.classify("Title", "Any content at all");

        // THEN there is nothing to match against, so general
        assertEquals("general", domain);
    }
}
