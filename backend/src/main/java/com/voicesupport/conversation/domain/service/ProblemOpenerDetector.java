package com.voicesupport.conversation.domain.service;

import java.text.Normalizer;
import java.util.Locale;
import java.util.Optional;
import java.util.regex.Pattern;

// BUG-025: a generic problem opener ("j'ai un problème avec ma facture", "I have a problem with my
// bill") states a topic but asks no concrete question. It retrieves a middling match that the
// post-generation grounding gate then deflects to an advisor hand-off. This detector flags such
// openers deterministically on the accent-folded turn so the InputGuardrail can redirect them to a
// TARGETED clarify — but ONLY when the turn carries no concrete question marker, so specific billing
// questions ("pourquoi ma facture a augmenté", "combien coûte le forfait") still reach retrieval.
// Patterns run on the normalized form (accents folded, apostrophes → spaces): "j'ai" → "j ai".
public class ProblemOpenerDetector {

    public enum Topic { BILLING, GENERAL }

    private static final Pattern PROBLEM_OPENER = compile(
            "\\b(probleme|problemes|souci|soucis|difficulte|difficultes|"
            + "problem|problems|issue|issues|trouble|concern)\\b");
    private static final Pattern HELP_OPENER = compile(
            "\\b(aidez moi|aide moi|besoin d aide|j ai besoin|help me|i need help|need help with)\\b");
    // A bare topic mention with nothing else ("ma facture", "my bill") is itself a vague opener.
    private static final Pattern BARE_TOPIC_OPENER = compile(
            "^(ma |mon |mes |my |la |le |une |un )?(facture|facturation|factures|bill|invoice|billing)$");
    // A concrete question marker (interrogative or a number) means the turn is specific enough to
    // retrieve and answer — it must NOT be short-circuited into the opener clarify.
    private static final Pattern SPECIFIC_MARKER = compile(
            "(\\b(pourquoi|comment|combien|quand|quel|quelle|quels|quelles|"
            + "why|how|when|which|what)\\b|[0-9])");
    // Distinguishes a billing opener (topic-aware clarify with billing options) from a general one.
    private static final Pattern BILLING_TOPIC = compile(
            "\\b(facture|facturation|factures|bill|bills|billing|invoice|invoices|"
            + "prelevement|prelevements|paiement|payment|montant|charge)\\b");

    // Returns the opener topic when the turn is a safe, generic problem/help opener with no concrete
    // question marker, or empty when the turn is specific or is not an opener at all.
    public Optional<Topic> detect(String question) {
        if (question == null) {
            return Optional.empty();
        }
        String normalized = normalize(question);
        if (normalized.isBlank() || SPECIFIC_MARKER.matcher(normalized).find()) {
            return Optional.empty();
        }
        if (!isOpener(normalized)) {
            return Optional.empty();
        }
        return Optional.of(BILLING_TOPIC.matcher(normalized).find() ? Topic.BILLING : Topic.GENERAL);
    }

    private boolean isOpener(String normalized) {
        return PROBLEM_OPENER.matcher(normalized).find()
                || HELP_OPENER.matcher(normalized).find()
                || BARE_TOPIC_OPENER.matcher(normalized).matches();
    }

    private static String normalize(String text) {
        String folded = Normalizer.normalize(text.toLowerCase(Locale.ROOT), Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "");
        return folded.replaceAll("[^a-z0-9]+", " ").strip();
    }

    private static Pattern compile(String regex) {
        return Pattern.compile("(?i)" + regex, Pattern.UNICODE_CASE);
    }
}
