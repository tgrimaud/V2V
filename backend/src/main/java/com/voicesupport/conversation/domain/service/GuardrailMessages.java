package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;

// Canned fallback wording (fr/en) for the guardrails. Language detection is delegated to the
// shared AnswerLanguage heuristic (TASK-BE-015) so the guardrail wording matches the language the
// LLM answer would use; English is the fallback so an ambiguous turn defers to the pilot default.
final class GuardrailMessages {

    private GuardrailMessages() {
    }

    static boolean isEnglish(String text) {
        return AnswerLanguage.detect(text, AnswerLanguage.ENGLISH) == AnswerLanguage.ENGLISH;
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

    // DEC-002: the assistant must never state a specific billing amount that is not backed
    // by source evidence. When the output guardrail catches an ungrounded amount, we drop
    // the generated text and offer a safe hand-off rather than voicing an invented figure.
    static String ungroundedAmount(String text) {
        return isEnglish(text)
                ? "I can't confirm a specific amount without checking your account. "
                  + "Would you like me to connect you with a support agent who can review your billing details?"
                : "Je ne peux pas confirmer de montant précis sans vérifier votre dossier. "
                  + "Souhaitez-vous que je vous mette en relation avec un conseiller qui pourra "
                  + "consulter le détail de votre facturation ?";
    }
}
