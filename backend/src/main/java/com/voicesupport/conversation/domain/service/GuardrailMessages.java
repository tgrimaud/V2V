package com.voicesupport.conversation.domain.service;

import java.util.regex.Pattern;

// Canned fallback wording (fr/en) and lightweight language detection shared by the
// input and post-retrieval guardrails. English is the fallback locale marker used by
// callers that request an explicit English answer.
final class GuardrailMessages {

    private static final Pattern ENGLISH_HINT = Pattern.compile(
            "\\b(the|is|are|what|how|can|do|does|my|your)\\b", Pattern.CASE_INSENSITIVE);

    private GuardrailMessages() {
    }

    static boolean isEnglish(String text) {
        return text.contains("(Please answer in English.)") || ENGLISH_HINT.matcher(text).find();
    }

    static String greeting(String text, boolean alreadyGreeted) {
        boolean english = isEnglish(text);
        if (alreadyGreeted) {
            return english ? "I'm listening, how can I help you?"
                    : "Je vous écoute, que puis-je faire pour vous ?";
        }
        return english ? "Hello! How can I help you today?"
                : "Bonjour ! Comment puis-je vous aider ?";
    }

    static String inappropriate(String text) {
        return isEnglish(text)
                ? "I cannot help with this type of request. I am a customer support assistant. "
                  + "Can I help you with something else regarding your account or our services?"
                : "Je ne suis pas en mesure de répondre à ce type de demande. "
                  + "Je suis un assistant de support client. "
                  + "Puis-je vous aider avec autre chose concernant votre compte ou nos services ?";
    }

    static String offTopic(String text) {
        return isEnglish(text)
                ? "This question is outside my area of expertise. I am a support assistant specialized "
                  + "in internet and telecom services. Can I help you with something else regarding your "
                  + "connection or our services?"
                : "Cette question sort de mon domaine de compétence. Je suis un assistant spécialisé dans "
                  + "le support client télécom (box internet et services associés). Puis-je vous aider avec "
                  + "autre chose concernant votre connexion ou nos services ?";
    }

    static String lowConfidence(String text) {
        return isEnglish(text)
                ? "I don't have enough reliable information to answer this question. "
                  + "Would you like me to connect you with a support agent?"
                : "Je n'ai pas assez d'informations fiables pour répondre à cette question. "
                  + "Souhaitez-vous que je vous mette en relation avec un conseiller ?";
    }
}
