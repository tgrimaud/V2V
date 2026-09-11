package com.voicesupport.billing.domain.service;

import java.text.Normalizer;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

// Deterministic, no-LLM billing-explanation intent guard (TASK-BE-045, ADR-0051 D2a). Matches
// accent-insensitive, word-boundary keywords (FR + EN) against the transcript so the dedicated
// billing endpoint (and, later, /converse routing) can decide whether a turn is a billing question
// without a runtime LLM classifier. The keyword set is injected (env-tunable) so it can be tuned per
// deployment without a code change. Word-boundary matching avoids the `contains()` false positives
// hit before (e.g. "ip" inside "équipement").
public class BillingIntentDetector {

    private final List<Pattern> keywordPatterns;

    public BillingIntentDetector(List<String> keywords) {
        this.keywordPatterns = keywords.stream()
                .map(BillingIntentDetector::fold)
                .filter(keyword -> !keyword.isBlank())
                .map(BillingIntentDetector::wordBoundaryPattern)
                .toList();
    }

    public boolean isBillingExplanationRequest(String transcript) {
        if (transcript == null || transcript.isBlank()) {
            return false;
        }
        String normalized = fold(transcript);
        return keywordPatterns.stream().anyMatch(pattern -> pattern.matcher(normalized).find());
    }

    private static Pattern wordBoundaryPattern(String keyword) {
        return Pattern.compile("\\b" + Pattern.quote(keyword) + "\\b");
    }

    // Lowercase + strip diacritics so "prélèvement" matches "prelevement" and case never matters.
    private static String fold(String text) {
        String decomposed = Normalizer.normalize(text, Normalizer.Form.NFD);
        return decomposed.replaceAll("\\p{M}+", "").toLowerCase(Locale.ROOT);
    }
}
