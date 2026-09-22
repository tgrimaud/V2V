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

    // BUG-025: a generic problem opener ("j'ai un problème avec ma facture", "I have a problem with
    // my bill") carries a topic but no concrete question, so it retrieves a middling match and the
    // post-generation grounding gate deflects it to a hand-off. Rather than transfer, ask a TARGETED
    // clarify that offers concrete options so the customer's next turn is specific enough to ground.
    static String problemOpenerClarify(AnswerLanguage language, boolean billing) {
        if (billing) {
            return english(language)
                    ? "I can help you with your bill. Could you tell me what the issue is: an amount "
                      + "that looks incorrect, an increase compared to last month, a charge you don't "
                      + "recognise, or a specific line on your invoice?"
                    : "Je peux vous aider au sujet de votre facture. Pouvez-vous préciser ce qui pose "
                      + "problème : un montant qui vous semble incorrect, une augmentation par rapport "
                      + "au mois dernier, un prélèvement que vous ne reconnaissez pas, ou une ligne "
                      + "précise de votre facture ?";
        }
        return english(language)
                ? "I can help. Could you tell me a bit more about what you need: is it about your bill, "
                  + "your subscription, a technical issue (router, connection), or something else?"
                : "Je peux vous aider. Pouvez-vous préciser votre demande : s'agit-il de votre facture, "
                  + "de votre abonnement, d'un problème technique (box, connexion), ou d'autre chose ?";
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
