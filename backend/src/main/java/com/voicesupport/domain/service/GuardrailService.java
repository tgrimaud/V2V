package com.voicesupport.domain.service;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.GuardrailResult;

import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

public class GuardrailService {

    private static final double DEFAULT_CONFIDENCE_THRESHOLD = 0.65;
    private static final int MIN_QUESTION_LENGTH = 3;

    private static final Set<Pattern> OFF_TOPIC_PATTERNS = Set.of(
            Pattern.compile("(?i)(quel(le)?\\s+(heure|temps|météo|température))", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(raconte|dis)[- ]moi\\s+(une\\s+)?(blague|histoire|poème)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(joue|chante|danse|dessine)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(qui\\s+est\\s+le\\s+président|capitale\\s+de)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(recette|cuisine|ingrédient)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(résult(at)?s?\\s+.{0,20}(foot|match|ligue|champion))", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(what('?s|\\s+is)\\s+the\\s+weather)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(tell\\s+me\\s+a\\s+(joke|story))", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(who\\s+(is|was)\\s+the\\s+president)", Pattern.UNICODE_CASE),
            Pattern.compile("(?i)(play|sing|draw|dance)\\s+(me\\s+)?", Pattern.UNICODE_CASE)
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
                "Je suis spécialisé dans le support client. " +
                "Puis-je vous aider avec autre chose concernant votre compte ou nos services ?";
        this.offTopicMessageEn = "This question is outside my area of expertise. " +
                "I specialize in customer support. " +
                "Can I help you with something else regarding your account or our services?";
        this.lowConfidenceMessageFr = "Je n'ai pas assez d'informations fiables pour répondre à cette question. " +
                "Souhaitez-vous que je vous mette en relation avec un conseiller ?";
        this.lowConfidenceMessageEn = "I don't have enough reliable information to answer this question. " +
                "Would you like me to connect you with a support agent?";
    }

    public GuardrailResult checkBeforeSearch(String question) {
        if (question == null || question.trim().length() < MIN_QUESTION_LENGTH) {
            return GuardrailResult.pass();
        }

        String trimmed = question.trim();
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

    private boolean isEnglish(String text) {
        return text.contains("(Please answer in English.)") ||
                Pattern.compile("\\b(the|is|are|what|how|can|do|does|my|your)\\b",
                        Pattern.CASE_INSENSITIVE).matcher(text).find();
    }
}
