package com.voicesupport.knowledge.infrastructure.adapter.out.classifier;

import com.voicesupport.knowledge.domain.port.out.AudienceClassifierPort;

import java.text.Normalizer;
import java.util.List;
import java.util.regex.Pattern;

// ADR-0034: deterministic, high-precision audience boundary for the mixed operator CSV corpus
// (ADR-0030), which has no audience column. An article is tagged "internal" (agent/back-office
// only) when its title/content matches an unambiguous agent-desk marker (e.g. "back office",
// "vérification d'aptitude", "R6/ION", whole-word acronyms VAA/VRD); otherwise "customer".
// Precision is preferred over recall: over-tagging customer content would hide legitimate
// answers, so only unambiguous markers tag internal. The retrieval boundary (fail-closed
// audience==customer filter) lives in PgVectorStoreAdapter. Markers are configurable so the
// boundary can be tuned without a rebuild; this port can later be swapped for an embedding
// implementation without touching the domain.
public class KeywordAudienceClassifierAdapter implements AudienceClassifierPort {

    public static final String CUSTOMER = "customer";
    public static final String INTERNAL = "internal";

    private final List<Pattern> internalMarkers;

    public KeywordAudienceClassifierAdapter(List<String> internalMarkers) {
        this.internalMarkers = internalMarkers.stream()
                .map(String::trim)
                .filter(marker -> !marker.isBlank())
                .map(KeywordAudienceClassifierAdapter::toMarkerPattern)
                .toList();
    }

    @Override
    public String classify(String title, String content) {
        String haystack = normalize((title == null ? "" : title) + " " + (content == null ? "" : content));
        if (haystack.isBlank()) {
            return CUSTOMER;
        }
        return internalMarkers.stream().anyMatch(p -> p.matcher(haystack).find()) ? INTERNAL : CUSTOMER;
    }

    // A bare alphanumeric acronym (VAA, VRD, R6) is matched on word boundaries to avoid false
    // positives inside unrelated words; multi-word markers ("back office") are matched literally.
    private static Pattern toMarkerPattern(String marker) {
        String normalized = normalize(marker);
        String quoted = Pattern.quote(normalized);
        String regex = normalized.matches("[a-z0-9]+") ? "\\b" + quoted + "\\b" : quoted;
        return Pattern.compile(regex);
    }

    // Lower-case + accent-fold so "Vérification d'Aptitude" matches "verification d'aptitude"
    // regardless of accents/case in the source article.
    private static String normalize(String text) {
        String lowered = text.toLowerCase(java.util.Locale.ROOT);
        return Normalizer.normalize(lowered, Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "");
    }
}
