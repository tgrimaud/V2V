package com.voicesupport.conversation.domain.model.valueobject;

import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.regex.Pattern;

// Answer language (TASK-BE-015): the language the assistant must speak on a given turn.
// V1 supports French and English; the enum owns the deterministic detection heuristic, the
// per-call LLM directive (with the exact hand-off sentence) and the hand-off markers the
// OutputGuardrail matches, so wording stays consistent across the LLM answer and the guardrails.
public enum AnswerLanguage {

    FRENCH("fr",
            "LANGUE : Tu dois répondre UNIQUEMENT en français, quelle que soit la langue du "
                    + "CONTEXTE ci-dessus. Appuie-toi sur le CONTEXTE pour aider le client même "
                    + "s'il ne traite le sujet que partiellement. Ne réponds \"Je n'ai pas cette "
                    + "information, je vous transfère à un conseiller.\" (exactement, mot pour mot) "
                    + "QUE si le CONTEXTE est vide ou totalement sans rapport avec la question.",
            List.of("transfère à un conseiller", "transfere a un conseiller"),
            "CONCISION : réponds en %d phrase(s) maximum, en allant droit au but, sans listes "
                    + "ni mise en forme ; garde uniquement l'information utile à la question."),
    ENGLISH("en",
            "LANGUAGE: You MUST answer ONLY in English, regardless of the language of the CONTEXT "
                    + "above. Use the CONTEXT to help the customer even if it only partially "
                    + "addresses the question. Reply \"I don't have this information, I'll transfer "
                    + "you to an advisor.\" (exactly, word for word) ONLY if the CONTEXT is empty or "
                    + "entirely unrelated to the question.",
            List.of("transfer you to an advisor"),
            "CONCISENESS: answer in %d sentence(s) maximum, get straight to the point, with no "
                    + "lists or formatting; keep only the information useful to the question.");

    private static final Pattern FRENCH_MARKERS = markers(
            "le", "la", "les", "un", "une", "des", "du", "je", "vous", "nous", "il", "elle",
            "est", "sont", "pourquoi", "comment", "quel", "quelle", "quels", "quelles", "ma",
            "mon", "mes", "votre", "vos", "ne", "pas", "plus", "avec", "sans", "pour", "dans",
            "facture", "bonjour", "merci", "pouvez", "avez", "puis", "ça", "où", "combien", "quand");
    private static final Pattern ENGLISH_MARKERS = markers(
            "the", "is", "are", "was", "were", "what", "how", "why", "when", "where", "can",
            "could", "do", "does", "did", "my", "your", "our", "with", "without", "for",
            "please", "help", "hello", "bill", "invoice", "internet", "connection", "you",
            "we", "they", "this", "that", "need", "want");
    private static final Pattern FRENCH_ACCENTS = Pattern.compile("[éèêëàâäçùûüîïôö]");
    private static final String ENGLISH_MARKER_HINT = "(please answer in english.)";

    private final String code;
    private final String llmDirective;
    private final List<String> handoffMarkers;
    private final String concisionTemplate;

    AnswerLanguage(String code, String llmDirective, List<String> handoffMarkers, String concisionTemplate) {
        this.code = code;
        this.llmDirective = llmDirective;
        this.handoffMarkers = handoffMarkers;
        this.concisionTemplate = concisionTemplate;
    }

    public String code() {
        return code;
    }

    public String llmDirective() {
        return llmDirective;
    }

    // Voice-first concision constraint (TASK-BE-018): a per-language, per-call instruction capping
    // the spoken answer to maxSentences so long grounded answers stop dominating TTS synthesis time
    // (batch TTFA and the live spoken tail). Language-owned so brevity wording matches the answer
    // language. A non-positive budget disables the constraint (empty string, nothing appended).
    public String concisionDirective(int maxSentences) {
        if (maxSentences <= 0) {
            return "";
        }
        return String.format(Locale.ROOT, concisionTemplate, maxSentences);
    }

    public List<String> handoffMarkers() {
        return handoffMarkers;
    }

    // Config parsing (TASK-BE-015): maps a language code (e.g. "en"/"fr") to the enum, defaulting
    // to English (the Eir pilot default) for any unknown/blank value.
    public static AnswerLanguage fromCode(String code) {
        if (code == null) {
            return ENGLISH;
        }
        String normalized = code.trim().toLowerCase(Locale.ROOT);
        for (AnswerLanguage language : values()) {
            if (language.code.equals(normalized)) {
                return language;
            }
        }
        return ENGLISH;
    }

    // Deterministic FR/EN detection: score distinct language markers on each side (French gets an
    // extra signal from accented characters) and pick the winner; on a tie or no signal, return
    // empty so an ambiguous turn defers to session stickiness or the configured default.
    public static Optional<AnswerLanguage> detect(String text) {
        if (text == null || text.isBlank()) {
            return Optional.empty();
        }
        String lower = text.toLowerCase(Locale.ROOT);
        if (lower.contains(ENGLISH_MARKER_HINT)) {
            return Optional.of(ENGLISH);
        }
        int french = count(FRENCH_MARKERS, lower) + accentSignal(lower);
        int english = count(ENGLISH_MARKERS, lower);
        if (french > english) {
            return Optional.of(FRENCH);
        }
        if (english > french) {
            return Optional.of(ENGLISH);
        }
        return Optional.empty();
    }

    private static int accentSignal(String lower) {
        return FRENCH_ACCENTS.matcher(lower).find() ? 1 : 0;
    }

    private static int count(Pattern pattern, String text) {
        return (int) pattern.matcher(text).results().count();
    }

    private static Pattern markers(String... words) {
        return Pattern.compile("\\b(" + String.join("|", words) + ")\\b",
                Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
    }
}
