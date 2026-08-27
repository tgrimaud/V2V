package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.ai.chat.client.ChatClient;

// OpenAI wording adapter (gpt-4o-mini), TASK-BE-033 benchmark candidate 4 (ADR-0045). Same
// grounded, DEC-002-safe contract and system prompt as the Mistral/Ollama adapters; only the
// provider wiring + telemetry tag differ. US chat egress is an OQ-009 compliance decision, not a
// latency one — this adapter only makes the candidate measurable behind the replaceable port.
public class OpenAiAnswerAdapter extends AbstractChatClientAnswerAdapter {

    private static final String PROVIDER = "openai";

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

    public OpenAiAnswerAdapter(
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
