package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;

// Canned fallback wording (fr/en) for the guardrails. The answer language is DECIDED once per
// turn by LanguageDetector (question language -> session stickiness -> configurable default) and
// passed in here, so the guardrail wording always matches the language the LLM answer uses —
// including on ambiguous turns where per-message detection alone would diverge (BUG-002).
final class GuardrailMessages {

    private GuardrailMessages() {
    }

    // French is the only non-default language in V1; anything else (English pilot default, or a
    // future language before its wording is added) falls back to the English wording.
    private static boolean english(AnswerLanguage language) {
        return language != AnswerLanguage.FRENCH;
    }

    static String greeting(AnswerLanguage language, boolean alreadyGreeted) {
        if (alreadyGreeted) {
            return english(language) ? "I'm listening, how can I help you?"
                    : "Je vous écoute, que puis-je faire pour vous ?";
        }
        return english(language) ? "Hello! How can I help you today?"
                : "Bonjour ! Comment puis-je vous aider ?";
    }

    static String inappropriate(AnswerLanguage language) {
        return english(language)
                ? "I cannot help with this type of request. I am a customer support assistant. "
                  + "Can I help you with something else regarding your account or our services?"
                : "Je ne suis pas en mesure de répondre à ce type de demande. "
                  + "Je suis un assistant de support client. "
                  + "Puis-je vous aider avec autre chose concernant votre compte ou nos services ?";
    }

    static String offTopic(AnswerLanguage language) {
        return english(language)
                ? "This question is outside my area of expertise. I am a support assistant specialized "
                  + "in internet and telecom services. Can I help you with something else regarding your "
                  + "connection or our services?"
                : "Cette question sort de mon domaine de compétence. Je suis un assistant spécialisé dans "
                  + "le support client télécom (box internet et services associés). Puis-je vous aider avec "
                  + "autre chose concernant votre connexion ou nos services ?";
    }

    // ADR-0034: a vague/low-information turn (e.g. "vas-y") or a middle-confidence retrieval does
    // not warrant an advisor hand-off — a short clarification usually resolves it. Distinct from
    // lowConfidence (below-floor hand-off) so the customer is invited to rephrase, not transferred.
    static String clarify(AnswerLanguage language) {
        return english(language)
                ? "I'm not sure I fully understood your request. "
                  + "Could you rephrase it or give me a little more detail?"
                : "Je ne suis pas sûr d'avoir bien compris votre demande. "
                  + "Pouvez-vous la reformuler ou me donner un peu plus de détails ?";
    }

    static String lowConfidence(AnswerLanguage language) {
        return english(language)
                ? "I don't have enough reliable information to answer this question. "
                  + "Would you like me to connect you with a support agent?"
                : "Je n'ai pas assez d'informations fiables pour répondre à cette question. "
                  + "Souhaitez-vous que je vous mette en relation avec un conseiller ?";
    }

    // DEC-002: the assistant must never state a specific billing amount that is not backed
    // by source evidence. When the output guardrail catches an ungrounded amount, we drop
    // the generated text and offer a safe hand-off rather than voicing an invented figure.
    static String ungroundedAmount(AnswerLanguage language) {
        return english(language)
                ? "I can't confirm a specific amount without checking your account. "
                  + "Would you like me to connect you with a support agent who can review your billing details?"
                : "Je ne peux pas confirmer de montant précis sans vérifier votre dossier. "
                  + "Souhaitez-vous que je vous mette en relation avec un conseiller qui pourra "
                  + "consulter le détail de votre facturation ?";
    }
}
