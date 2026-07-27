package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;

import java.text.Normalizer;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

// Pre-retrieval guardrail (ADR-0014 / ADR-0034): handles greetings directly, asks to clarify on a
// vague/low-information turn, and refuses off-topic or unsafe requests with a canned response,
// before any embedding, vector search or LLM call is made. Deterministic and language-aware (fr/en).
public class InputGuardrail {

    private static final int MIN_QUESTION_LENGTH = 3;
    // A turn made only of contentless continuers ("vas-y", "ok"...) carries no retrievable intent;
    // answering it retrieves a weak, possibly wrong-audience match (BUG-005). Max 3 such tokens so a
    // real short question is never mistaken for a vague turn. Configurable per deployment.
    private static final int MAX_VAGUE_TOKENS = 3;
    private static final Set<String> DEFAULT_VAGUE_MARKERS = Set.of(
            "vas-y", "vas y", "allez-y", "allez y", "continue", "continuez", "poursuis", "poursuivez",
            "ensuite", "la suite", "go", "go on", "go ahead", "ok", "okay", "d'accord", "dac", "dacc",
            "alors", "donc", "bah", "ben", "euh", "hmm", "voila", "voilà", "et");

    private static final List<Pattern> GREETING_PATTERNS = List.of(
            compile("^(bonjour|bonsoir|salut|coucou|hey|hello|hi|yo|bjr|slt|cc|bsr)\\s*[!.?,;…]*$"),
            compile("^(bonjour|salut|hello|hi|hey|bjr|slt)\\s+([a-zéèà]+\\s*[!.?,;…]*)$"),
            compile("^(comment\\s+(ça\\s+va|allez[- ]vous)|how\\s+are\\s+you|[çc]a\\s+va)\\s*[?!.,;…]*$"));

    private static final List<Pattern> INAPPROPRIATE_PATTERNS = List.of(
            compile("(arme|weapon|gun|bomb|explos|firearm|fusil|pistolet|grenade)"),
            compile("(drogue|drug|cocaïne|héroïne|meth|crack|stupéfiant)"),
            compile("(tuer|kill|murder|assassin|suicide)"),
            compile("(fabriquer|construire|build|make|create).{0,20}(bombe|arme|weapon|explosive|poison)"),
            compile("(pédophil|child\\s+(porn|abuse))"),
            compile("(terroris|radicalisation|attentat)"));

    // BUG-001: cyber-security terms (phishing, scam, malware, hacking...) are legitimate SUPPORT
    // topics — "what to do about scam/phishing calls", "how to protect against malware". They are
    // unsafe only when the user wants to PERFORM an attack: an offensive action verb is present AND
    // no defensive framing is. Defensive questions carry a protect/avoid/report marker (or no
    // offensive verb at all) and reach retrieval instead of being refused.
    private static final Pattern CYBER_ATTACK_TERM = compile(
            "\\b(phishing|hame[çc]onnage|scam|arnaque|hack(er|ing|é|ed|s)?|pirat(age|er|é)|"
            + "ransomware|ran[çc]ongiciel|malware|spyware|logiciel\\s+(malveillant|espion)|keylogger|"
            + "ddos|botnet|cheval\\s+de\\s+troie|trojan|virus\\s+informatique)\\b");
    private static final Pattern CYBER_OFFENSE_VERB = compile(
            "\\b(mener|lancer|créer|creer|monter|fabriquer|construire|développer|developper|coder|"
            + "programmer|déployer|deployer|écrire|ecrire|pirater|hacker|"
            + "run|launch|create|build|perform|conduct|develop|deploy|write|hack)\\b");
    private static final Pattern CYBER_DEFENSE_MARKER = compile(
            "(prot[ée]g|protect|[ée]vit|avoid|prevent|emp[êe]ch|reconna[îi]|recogni|d[ée]tect|"
            + "signal|report|d[ée]clar|victim|fraud|frauduleux|se\\s+d[ée]fend|defend|s[ée]curis|"
            + "secur|safe|bloqu|block|spam|suspect|m[ée]fi|"
            + "que\\s+faire|what\\s+(should\\s+i|to)\\s+do|comment\\s+(faire\\s+)?(face|contre)|"
            + "face\\s+[àa])");

    private static final List<Pattern> OFF_TOPIC_PATTERNS = List.of(
            compile("(météo|meteo|weather|forecast|prévisions?\\s+météo)"),
            compile("(quel(le)?\\s+temps\\s+(fait|fera|qu'?il))"),
            compile("(quelle?\\s+heure|what\\s+time)"),
            compile("(blague|joke|histoire\\s+drôle|devinette|riddle)"),
            compile("(raconte|dis)[- ]moi\\s+(une\\s+)?(blague|histoire|poème)"),
            compile("\\b(joue|chante|danse|dessine|play|sing|draw|dance)\\b"),
            compile("(président|president|capitale|capital\\s+of|roi|queen|king)"),
            compile("(recette|cuisine|ingrédient|recipe|cook(ing)?)"),
            compile("(foot(ball)?|rugby|tennis|basket|match\\s+de|ligue|champion(nat)?|tour\\s+de\\s+france)"),
            compile("\\b(film|cinéma|movie|musique|chanson|album|concert)\\b"),
            compile("(horoscope|astro(logie|logy)|signe\\s+(du\\s+)?zodiaque)"),
            compile("(bourse|bitcoin|crypto|trading|investir|actions?\\s+en\\s+bourse)"),
            compile("(recette|jeu(x)?\\s+vidéo|gaming|playstation|xbox|nintendo)"),
            compile("(tradui(s|re|ction)|translate)"),
            compile("(qui\\s+(est|a\\s+inventé|était)|who\\s+(is|was|invented))"));

    // Normalized (lower-case, accent-folded, punctuation→space) marker forms: whole-utterance
    // phrases (e.g. "vas y", "d accord") and single-token continuers (e.g. "ok", "alors").
    private final Set<String> vaguePhrases;
    private final Set<String> vagueTokens;

    public InputGuardrail() {
        this(DEFAULT_VAGUE_MARKERS);
    }

    public InputGuardrail(Collection<String> vagueMarkers) {
        Set<String> phrases = new HashSet<>();
        Set<String> tokens = new HashSet<>();
        for (String marker : vagueMarkers) {
            String normalized = normalize(marker);
            if (normalized.isBlank()) {
                continue;
            }
            phrases.add(normalized);
            if (!normalized.contains(" ")) {
                tokens.add(normalized);
            }
        }
        this.vaguePhrases = Set.copyOf(phrases);
        this.vagueTokens = Set.copyOf(tokens);
    }

    // The answer language is decided once per turn upstream (LanguageDetector: question language,
    // then session stickiness, then the configurable default) and passed in so the canned wording
    // matches the language of the rest of the turn, even when the input itself is ambiguous.
    public GuardrailDecision check(String question, boolean alreadyGreeted, AnswerLanguage language) {
        if (question == null || question.isBlank()) {
            return GuardrailDecision.pass();
        }
        String trimmed = question.trim();
        if (matchesAny(GREETING_PATTERNS, trimmed)) {
            return GuardrailDecision.greeting(GuardrailMessages.greeting(language, alreadyGreeted));
        }
        if (isVague(trimmed)) {
            return GuardrailDecision.clarify(GuardrailMessages.clarify(language));
        }
        if (trimmed.length() < MIN_QUESTION_LENGTH) {
            return GuardrailDecision.pass();
        }
        if (matchesAny(INAPPROPRIATE_PATTERNS, trimmed) || isCyberOffense(trimmed)) {
            return GuardrailDecision.inappropriate(GuardrailMessages.inappropriate(language));
        }
        if (matchesAny(OFF_TOPIC_PATTERNS, trimmed)) {
            return GuardrailDecision.offTopic(GuardrailMessages.offTopic(language));
        }
        return GuardrailDecision.pass();
    }

    // A turn is vague when the whole utterance is a known continuer phrase, or when it is a short
    // run (<= MAX_VAGUE_TOKENS) made entirely of continuer tokens — so "ok" or "vas-y, continue"
    // clarify, while "ok how do I pay?" (real intent) is answered normally.
    private boolean isVague(String text) {
        String normalized = normalize(text);
        if (normalized.isBlank()) {
            return false;
        }
        if (vaguePhrases.contains(normalized)) {
            return true;
        }
        String[] words = normalized.split(" ");
        return words.length <= MAX_VAGUE_TOKENS && allVagueTokens(words);
    }

    // BUG-001: a cyber-security term is unsafe only when the turn expresses intent to PERFORM the
    // attack (an offensive verb) and carries no defensive framing (protect/avoid/report/victim...).
    // "What should I do about scam or phishing calls?" and "how to protect against malware" pass;
    // "how do I run a phishing campaign" / "comment créer un ransomware" stay refused.
    private boolean isCyberOffense(String text) {
        if (!CYBER_ATTACK_TERM.matcher(text).find()) {
            return false;
        }
        if (CYBER_DEFENSE_MARKER.matcher(text).find()) {
            return false;
        }
        return CYBER_OFFENSE_VERB.matcher(text).find();
    }

    private boolean allVagueTokens(String[] words) {
        for (String word : words) {
            if (!vagueTokens.contains(word)) {
                return false;
            }
        }
        return true;
    }

    private static String normalize(String text) {
        String folded = Normalizer.normalize(text.toLowerCase(java.util.Locale.ROOT), Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "");
        return folded.replaceAll("[^a-z0-9]+", " ").strip();
    }

    private boolean matchesAny(List<Pattern> patterns, String text) {
        return patterns.stream().anyMatch(p -> p.matcher(text).find());
    }

    private static Pattern compile(String regex) {
        return Pattern.compile("(?i)" + regex, Pattern.UNICODE_CASE);
    }
}
