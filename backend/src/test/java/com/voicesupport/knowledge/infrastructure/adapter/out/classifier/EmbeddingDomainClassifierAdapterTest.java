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
    void shouldDegradeToGeneralWhenEmbeddingFails() {
        // GIVEN an embedding backend that fails on the article text (anchors still embed at construction)
        FakeEmbeddingModel model = embeddingModelWithOrthogonalAnchors().failOn("invoice");
        EmbeddingDomainClassifierAdapter classifier =
                new EmbeddingDomainClassifierAdapter(model, ANCHORS, 0.5, 2000);

        // WHEN classification hits the transient failure
        String domain = classifier.classify("Bill", "A question about my invoice");

        // THEN one failing article does not abort ingestion; it degrades to general
        assertEquals("general", domain);
    }

    @Test
    void shouldNormaliseSimilarityByBothVectorMagnitudes() {
        // GIVEN a HALF-magnitude billing anchor ([0.5,0,0]) and an article aligned with it ([1,0,0]).
        // Cosine = dot/(|q|*|anchor|) = 0.5/(1*0.5) = 1.0 (>= 0.5). If the two magnitudes were divided
        // instead of multiplied in the denominator, it would be 0.5/(1/0.5) = 0.25 (< 0.5) -> general.
        FakeEmbeddingModel model = new FakeEmbeddingModel()
                .on("BILLING_ANCHOR", new float[]{0.5f, 0f, 0f})
                .on("SUPPORT_ANCHOR", new float[]{0f, 1f, 0f})
                .on("COMMERCIAL_ANCHOR", new float[]{0f, 0f, 1f})
                .on("halfbill", new float[]{1f, 0f, 0f});
        EmbeddingDomainClassifierAdapter classifier =
                new EmbeddingDomainClassifierAdapter(model, ANCHORS, 0.5, 2000);

        // WHEN classifying
        String domain = classifier.classify("t", "aligned halfbill vector");

        // THEN both magnitudes normalise the score; a multiply->divide mutant on the norm product
        // would drop it below threshold and fall back to general.
        assertEquals("billing", domain);
    }

    @Test
    void shouldSelectAnchorWhenSimilarityExactlyEqualsThreshold() {
        // GIVEN an article perfectly aligned with billing (cosine 1.0) and a threshold of exactly 1.0
        FakeEmbeddingModel model = embeddingModelWithOrthogonalAnchors()
                .on("exactbill", new float[]{1f, 0f, 0f});
        EmbeddingDomainClassifierAdapter classifier =
                new EmbeddingDomainClassifierAdapter(model, ANCHORS, 1.0, 2000);

        // WHEN classifying
        String domain = classifier.classify("t", "exactbill match");

        // THEN a score equal to the current best is accepted (>=); a strict `>` mutant would leave it general
        assertEquals("billing", domain);
    }

    @Test
    void shouldClassifyFromTheTitleWhenOnlyTheTitleCarriesTheSignal() {
        // GIVEN the classifying keyword lives in the TITLE only, the content is neutral
        FakeEmbeddingModel model = embeddingModelWithOrthogonalAnchors()
                .on("titlekey", new float[]{1f, 0f, 0f});
        EmbeddingDomainClassifierAdapter classifier =
                new EmbeddingDomainClassifierAdapter(model, ANCHORS, 0.5, 2000);

        // WHEN classifying with the signal in the title
        String domain = classifier.classify("about titlekey", "neutral body without any anchor");

        // THEN the title is part of the classification text; a mutant that drops the title (negated
        // null-guard branch) would embed only the neutral body and fall back to general.
        assertEquals("billing", domain);
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
