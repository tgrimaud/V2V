package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.ai.chat.client.ChatClient;

// Mistral wording adapter (mistral-small-latest), the development default provider (DEC-011).
public class MistralAnswerAdapter extends AbstractChatClientAnswerAdapter {

    private static final String PROVIDER = "mistral-api";

    // Trimmed for latency (TASK-BE-011): a shorter system prompt means fewer prefill tokens, hence
    // a faster LLM time-to-first-token. All DEC-002 rules are preserved. The answer language and the
    // exact hand-off sentence are appended per call as the AnswerLanguage directive (TASK-BE-015),
    // so the assistant answers in the customer's language (the OutputGuardrail matches both FR/EN
    // hand-off markers) instead of being biased to French by this prompt.
    private static final String SYSTEM_PROMPT = """
            Tu es un agent de support client Telecom/FAI (box internet, mobile, facturation). \
            Réponds en style vocal : phrases courtes, claires, polies et empathiques.

            Règles ABSOLUES :
            - Réponds UNIQUEMENT à partir du CONTEXTE ci-dessous ; n'invente rien.
            - Exploite le CONTEXTE pour aider le client même s'il ne traite le sujet que \
            partiellement ; ne renvoie vers un conseiller que si le CONTEXTE est vide ou sans \
            rapport avec la question.
            - N'annonce JAMAIS un montant ou tarif absent du CONTEXTE ; propose plutôt de vérifier \
            le dossier avec un conseiller.
            - Ne salue pas si un échange a déjà eu lieu.

            CONTEXTE :
            {context}
            """;

    public MistralAnswerAdapter(
            ChatClient chatClient, BackendTelemetry telemetry, long timeoutMs,
            long streamTimeoutMs, int maxAnswerSentences) {
        super(chatClient, telemetry, timeoutMs, streamTimeoutMs, maxAnswerSentences);
    }

    @Override
    protected String systemPromptTemplate() {
        return SYSTEM_PROMPT;
    }

    @Override
    protected String providerName() {
        return PROVIDER;
    }
}
