package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.ai.chat.client.ChatClient;

// Ollama wording adapter, the local/offline alternative provider (DEC-011). Same grounded,
// DEC-002-safe contract as the Mistral adapter; only the provider wiring differs.
public class OllamaAnswerAdapter extends AbstractChatClientAnswerAdapter {

    private static final String PROVIDER = "ollama";

    // Trimmed for latency (TASK-BE-011): a shorter system prompt means fewer prefill tokens, hence
    // a faster LLM time-to-first-token. All DEC-002 rules are preserved verbatim in intent, and the
    // exact hand-off sentence the OutputGuardrail matches ("transfère à un conseiller") is kept.
    private static final String SYSTEM_PROMPT = """
            Tu es un agent de support client Telecom/FAI (box internet, mobile, facturation). \
            Réponds en style vocal : phrases courtes, claires, polies et empathiques.

            Règles ABSOLUES :
            - Réponds UNIQUEMENT à partir du CONTEXTE ci-dessous ; n'invente rien.
            - N'annonce JAMAIS un montant ou tarif absent du CONTEXTE ; propose plutôt de vérifier \
            le dossier avec un conseiller.
            - Si le CONTEXTE ne contient pas la réponse, dis exactement : \
            "Je n'ai pas cette information, je vous transfère à un conseiller."
            - Réponds dans la langue de la question.
            - Ne salue pas si un échange a déjà eu lieu.

            CONTEXTE :
            {context}
            """;

    public OllamaAnswerAdapter(ChatClient chatClient, BackendTelemetry telemetry, long timeoutMs) {
        super(chatClient, telemetry, timeoutMs);
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
