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
    // retrieve and answer — it must NOT be short-circuited into the opener clarify. On the GENERAL
    // path this still fully bypasses the clarify (unchanged).
    private static final Pattern SPECIFIC_MARKER = compile(
            "(\\b(pourquoi|comment|combien|quand|quel|quelle|quels|quelles|"
            + "why|how|when|which|what)\\b|[0-9])");
    // US-043 / TASK-BE-070 (increment D): on the BILLING path an interrogative alone is only a WEAK
    // marker — a bare "why/how do I have a bill problem" is still under-specified and should be
    // clarified. Only a concrete AMOUNT anchor (a number, or a spelled-out "euro(s)") makes a
    // billing opener answerable ("ma facture a augmenté de 10 euros") and lets it bypass the clarify.
    // Payment-mechanic broadening is intentionally deferred to the diagnostic increment (TASK-BE-071).
    private static final Pattern CONCRETE_BILLING_ANCHOR = compile("([0-9]|\\b(euro|euros)\\b)");
    // Distinguishes a billing opener (topic-aware clarify with billing options) from a general one.
    private static final Pattern BILLING_TOPIC = compile(
            "\\b(facture|facturation|factures|bill|bills|billing|invoice|invoices|"
            + "prelevement|prelevements|paiement|payment|montant|charge)\\b");
    // An explicit human/advisor request must NOT be intercepted by the opener clarify: let it flow
    // to the normal pipeline so the escalation path (ADR-0019) handles it, even if the turn also
    // carries a generic problem word ("j'ai un problème, je veux un conseiller").
    private static final Pattern ESCALATION_REQUEST = compile(
            "\\b(conseiller|conseillere|un agent|une personne|un humain|quelqu un|"
            + "advisor|a human|an agent|real person|someone)\\b|"
            + "\\b(parler|joindre|contacter|speak|talk|transfer|escalate)\\b");

    // Returns the opener topic when the turn is a safe problem/help/bare-topic opener that is still
    // under-specified, or empty when the turn is specific enough to retrieve, is an escalation
    // request, or is not an opener at all. BILLING and GENERAL use different specificity gates
    // (see classify): billing clarifies on a weak interrogative, general still bypasses on any marker.
    public Optional<Topic> detect(String question) {
        if (question == null) {
            return Optional.empty();
        }
        String normalized = normalize(question);
        if (normalized.isBlank() || ESCALATION_REQUEST.matcher(normalized).find() || !isOpener(normalized)) {
            return Optional.empty();
        }
        return classify(normalized);
    }

    private Optional<Topic> classify(String normalized) {
        if (BILLING_TOPIC.matcher(normalized).find()) {
            // Increment D: an under-specified billing opener is clarified even with a weak marker;
            // only a concrete amount anchor makes it answerable and bypasses the clarify.
            return CONCRETE_BILLING_ANCHOR.matcher(normalized).find() ? Optional.empty() : Optional.of(Topic.BILLING);
        }
        // GENERAL path unchanged: any concrete question marker (interrogative/number) bypasses.
        return SPECIFIC_MARKER.matcher(normalized).find() ? Optional.empty() : Optional.of(Topic.GENERAL);
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
