package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;

import java.util.List;
import java.util.regex.Pattern;

// Pre-retrieval guardrail (ADR-0014): handles greetings directly and refuses
// off-topic or unsafe requests with a canned response, before any embedding,
// vector search or LLM call is made. Deterministic and language-aware (fr/en).
public class InputGuardrail {

    private static final int MIN_QUESTION_LENGTH = 3;

    private static final List<Pattern> GREETING_PATTERNS = List.of(
            compile("^(bonjour|bonsoir|salut|coucou|hey|hello|hi|yo|bjr|slt|cc|bsr)\\s*[!.?,;…]*$"),
            compile("^(bonjour|salut|hello|hi|hey|bjr|slt)\\s+([a-zéèà]+\\s*[!.?,;…]*)$"),
            compile("^(comment\\s+(ça\\s+va|allez[- ]vous)|how\\s+are\\s+you|[çc]a\\s+va)\\s*[?!.,;…]*$"));

    private static final List<Pattern> INAPPROPRIATE_PATTERNS = List.of(
            compile("(arme|weapon|gun|bomb|explos|firearm|fusil|pistolet|grenade)"),
            compile("(drogue|drug|cocaïne|héroïne|meth|crack|stupéfiant)"),
            compile("(tuer|kill|murder|assassin|suicide)"),
            compile("(hack(er|ing)?|pirater|phishing|ransomware|malware)"),
            compile("(fabriquer|construire|build|make|create).{0,20}(bombe|arme|weapon|explosive|poison)"),
            compile("(pédophil|child\\s+(porn|abuse))"),
            compile("(terroris|radicalisation|attentat)"));

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

    public GuardrailDecision check(String question, boolean alreadyGreeted) {
        if (question == null || question.isBlank()) {
            return GuardrailDecision.pass();
        }
        String trimmed = question.trim();
        if (matchesAny(GREETING_PATTERNS, trimmed)) {
            return GuardrailDecision.greeting(GuardrailMessages.greeting(trimmed, alreadyGreeted));
        }
        if (trimmed.length() < MIN_QUESTION_LENGTH) {
            return GuardrailDecision.pass();
        }
        if (matchesAny(INAPPROPRIATE_PATTERNS, trimmed)) {
            return GuardrailDecision.inappropriate(GuardrailMessages.inappropriate(trimmed));
        }
        if (matchesAny(OFF_TOPIC_PATTERNS, trimmed)) {
            return GuardrailDecision.offTopic(GuardrailMessages.offTopic(trimmed));
        }
        return GuardrailDecision.pass();
    }

    private boolean matchesAny(List<Pattern> patterns, String text) {
        return patterns.stream().anyMatch(p -> p.matcher(text).find());
    }

    private static Pattern compile(String regex) {
        return Pattern.compile("(?i)" + regex, Pattern.UNICODE_CASE);
    }
}
