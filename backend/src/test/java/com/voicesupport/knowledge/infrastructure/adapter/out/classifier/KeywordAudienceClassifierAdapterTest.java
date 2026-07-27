package com.voicesupport.knowledge.infrastructure.adapter.out.classifier;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DisplayName("KeywordAudienceClassifierAdapter (ADR-0034 / BUG-005)")
class KeywordAudienceClassifierAdapterTest {

    private final KeywordAudienceClassifierAdapter classifier = new KeywordAudienceClassifierAdapter(
            List.of("back office", "vérification d'aptitude", "r6/ion", "vaa", "vrd"));

    @Test
    @DisplayName("tags the BUG-005 agent-desk article (R6/ION + VAA) as internal")
    void tags_agent_desk_article_as_internal() {
        String content = "Modify the appointment in R6/ION for Back Office agents. "
                + "Check availability via the VAA screen.";

        assertEquals("internal", classifier.classify("View Available Appointments (VAA)", content));
    }

    @Test
    @DisplayName("matches internal markers regardless of case and accents")
    void matches_regardless_of_case_and_accents() {
        assertEquals("internal", classifier.classify("Procédure", "Faire la Vérification d'Aptitude puis valider."));
        assertEquals("internal", classifier.classify(null, "process for BACK OFFICE only"));
    }

    @Test
    @DisplayName("keeps a plain customer billing article as customer")
    void keeps_customer_article_as_customer() {
        String content = "Your monthly bill can increase when a promotional discount ends "
                + "or when you use more data than your plan includes.";

        assertEquals("customer", classifier.classify("Why did my bill increase?", content));
    }

    @Test
    @DisplayName("acronyms match on word boundaries: an acronym embedded in a longer token does not match")
    void does_not_false_positive_on_embedded_acronym() {
        // "vaa" appears inside "bravaado" and "vrd" inside "overvrding" — word-boundary matching
        // must not treat these as the standalone internal acronyms.
        String content = "He answered with bravaado while overvrding the customer request.";

        assertEquals("customer", classifier.classify("Customer note", content));
    }

    @Test
    @DisplayName("blank input defaults to the customer audience")
    void blank_defaults_to_customer() {
        assertEquals("customer", classifier.classify(null, null));
        assertEquals("customer", classifier.classify("", "   "));
    }

    @Test
    @DisplayName("a marker present only in the title (empty content) still tags internal")
    void tags_internal_when_marker_is_in_title_only() {
        // GIVEN — the internal marker is in the title and the content is empty; the title must
        // be part of the haystack (pins `title == null ? "" : title`, not dropping the title).
        String internalTitle = "Back Office procedure (VAA)";

        // WHEN
        String audience = classifier.classify(internalTitle, "");

        // THEN
        assertEquals("internal", audience);
    }

    @Test
    @DisplayName("a blank marker in the config is ignored (does not turn every article internal)")
    void ignores_blank_markers() {
        // GIVEN — a blank marker must be filtered out at construction; if kept, its empty pattern
        // would match every haystack and mis-tag all content as internal (fail-open).
        KeywordAudienceClassifierAdapter withBlank =
                new KeywordAudienceClassifierAdapter(List.of("back office", "   "));

        // WHEN
        String audience = withBlank.classify("Why did my bill increase?", "Your monthly bill can increase.");

        // THEN
        assertEquals("customer", audience);
    }
}
