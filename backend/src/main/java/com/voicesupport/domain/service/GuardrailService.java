package com.voicesupport.domain.service;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.GuardrailResult;

import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

public class GuardrailService {

    private static final double DEFAULT_CONFIDENCE_THRESHOLD = 0.65;
    private static final int MIN_QUESTION_LENGTH = 3;

    private static final Set<Pattern> GREETING_PATTERNS = Set.of(
            Pattern.compile("(?i)^(bonjour|bonsoir|salut|coucou|hey|hello|hi|yo|bjr|slt|cc|bsr)\\s*[!.?,;…]*$", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)^(bonjour|salut|hello|hi|hey|bjr|slt)\\s+([a-zéèà]+\\s*[!.?,;…]*)$", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)^(comment\\s+(ça\\s+va|allez[- ]vous)|how\\s+are\\s+you|[çc]a\\s+va)\\s*[?!.,;…]*$", Pattern.UNICODE_CASE)
    );

    private static final Set<Pattern> OFF_TOPIC_PATTERNS = Set.of(
            Pattern.compile("(?i)(météo|meteo|weather|forecast|prévisions?\\s+météo)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(quel(le)?\\s+temps\\s+(fait|fera|qu'?il))", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(quelle?\\s+heure|what\\s+time)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(blague|joke|histoire\\s+drôle|devinette|riddle)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(raconte|dis)[- ]moi\\s+(une\\s+)?(blague|histoire|poème)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)\\b(joue|chante|danse|dessine|play|sing|draw|dance)\\b", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(président|president|capitale|capital\\s+of|roi|queen|king)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(recette|cuisine|ingrédient|recipe|cook(ing)?)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(foot(ball)?|rugby|tennis|basket|match\\s+de|ligue|champion(nat)?|tour\\s+de\\s+france)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)\\b(film|cinéma|movie|musique|chanson|album|concert)\\b", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(horoscope|astro(logie|logy)|signe\\s+(du\\s+)?zodiaque)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(politique|élection|election|vote(r|z)\\b|parti\\s+(politique|socialiste|républicain))", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(bourse|bitcoin|crypto|trading|investir|actions?\\s+en\\s+bourse)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(vacances|voyage|hôtel|hotel|avion|flight|destination\\s+de)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(jeu(x)?\\s+vidéo|gaming|playstation|xbox|nintendo|fortnite)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(programme\\s+tv|émission|netflix|disney\\+)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(santé|médecin|doctor|symptôme|maladie|médicament|ordonnance)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(programm(er|ation|ing)|python|javascript|react|angular)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(tradui(s|re|ction)|translate)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(équation|equation|combien\\s+font|résoudre\\s+(un|ce)\\s+calcul)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(qui\\s+(est|a\\s+inventé|était)|who\\s+(is|was|invented))", Pattern.UNICODE_CASE)
    );

    private static final Set<Pattern> INAPPROPRIATE_PATTERNS = Set.of(
            Pattern.compile("(?i)(arme|weapon|gun|bomb|explos|firearm|fusil|pistolet|grenade)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(drogue|drug|cocaïne|héroïne|meth|crack|stupéfiant)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(tuer|kill|murder|assassin|suicide|mourir)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(hack(er|ing)?|pirater|phishing|ransomware|malware)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(fabriquer|construire|build|make|create).{0,20}(bombe|arme|weapon|explosive|poison)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(contenu\\s+(illégal|interdit)|illegal\\s+content)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(pédophil|child\\s+(porn|abuse)|exploitation)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(terroris|radicalisation|attentat)", Pattern.UNICODE_CASE)
    );

    private final double confidenceThreshold;
    private final String offTopicMessageFr;
    private final String offTopicMessageEn;
    private final String lowConfidenceMessageFr;
    private final String lowConfidenceMessageEn;

    public GuardrailService() {
        this(DEFAULT_CONFIDENCE_THRESHOLD);
    }

    public GuardrailService(double confidenceThreshold) {
        this.confidenceThreshold = confidenceThreshold;
        this.offTopicMessageFr = "Cette question sort de mon domaine de compétence. " +
                "Je suis un assistant spécialisé dans le support client pour les problèmes de box internet et services associés. " +
                "Puis-je vous aider avec autre chose concernant votre connexion ou nos services ?";
        this.offTopicMessageEn = "This question is outside my area of expertise. " +
                "I am a support assistant specialized in internet box issues and related services. " +
                "Can I help you with something else regarding your connection or our services?";
        this.lowConfidenceMessageFr = "Je n'ai pas assez d'informations fiables pour répondre à cette question. " +
                "Souhaitez-vous que je vous mette en relation avec un conseiller ?";
        this.lowConfidenceMessageEn = "I don't have enough reliable information to answer this question. " +
                "Would you like me to connect you with a support agent?";
    }

    public GuardrailResult checkBeforeSearch(String question) {
        return checkBeforeSearch(question, false);
    }

    public GuardrailResult checkBeforeSearch(String question, boolean alreadyGreeted) {
        if (question == null || question.trim().isEmpty()) {
            return GuardrailResult.pass();
        }

        String trimmed = question.trim();

        for (Pattern pattern : GREETING_PATTERNS) {
            if (pattern.matcher(trimmed).find()) {
                return GuardrailResult.greeting(greetingMessage(trimmed, alreadyGreeted));
            }
        }

        if (trimmed.length() < MIN_QUESTION_LENGTH) {
            return GuardrailResult.pass();
        }

        for (Pattern pattern : INAPPROPRIATE_PATTERNS) {
            if (pattern.matcher(trimmed).find()) {
                String message = isEnglish(trimmed)
                        ? "I cannot help with this type of request. " +
                          "I am a customer support assistant. " +
                          "Can I help you with something else regarding your account or our services?"
                        : "Je ne suis pas en mesure de répondre à ce type de demande. " +
                          "Je suis un assistant de support client. " +
                          "Puis-je vous aider avec autre chose concernant votre compte ou nos services ?";
                return GuardrailResult.inappropriate(message);
            }
        }

        for (Pattern pattern : OFF_TOPIC_PATTERNS) {
            if (pattern.matcher(trimmed).find()) {
                String message = isEnglish(trimmed) ? offTopicMessageEn : offTopicMessageFr;
                return GuardrailResult.offTopic(message);
            }
        }

        return GuardrailResult.pass();
    }

    public GuardrailResult checkAfterSearch(String question, List<Citation> citations) {
        if (citations == null || citations.isEmpty()) {
            String message = isEnglish(question) ? lowConfidenceMessageEn : lowConfidenceMessageFr;
            return GuardrailResult.lowConfidence(message);
        }

        double bestScore = citations.stream()
                .mapToDouble(Citation::score)
                .max()
                .orElse(0.0);

        if (bestScore < confidenceThreshold) {
            String message = isEnglish(question) ? lowConfidenceMessageEn : lowConfidenceMessageFr;
            return GuardrailResult.lowConfidence(message);
        }

        return GuardrailResult.pass();
    }

    private String greetingMessage(String trimmed, boolean alreadyGreeted) {
        boolean english = isEnglish(trimmed);
        if (alreadyGreeted) {
            return english
                    ? "I'm listening, how can I help you?"
                    : "Je vous écoute, que puis-je faire pour vous ?";
        }
        return english
                ? "Hello! How can I help you today?"
                : "Bonjour ! Comment puis-je vous aider ?";
    }

    private boolean isEnglish(String text) {
        return text.contains("(Please answer in English.)") ||
                Pattern.compile("\\b(the|is|are|what|how|can|do|does|my|your)\\b",
                        Pattern.CASE_INSENSITIVE).matcher(text).find();
    }
}
