package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import org.springframework.ai.chat.client.ChatClient;

// Ollama wording adapter, the local/offline alternative provider (DEC-011). Same grounded,
// DEC-002-safe contract as the Mistral adapter; only the provider wiring differs.
public class OllamaAnswerAdapter extends AbstractChatClientAnswerAdapter {

    private static final String SYSTEM_PROMPT = """
            Tu es un agent de support client pour un opérateur Telecom/FAI (box internet, mobile, \
            facturation). Tu réponds au client de façon claire, concise et professionnelle, adaptée \
            à une conversation vocale (phrases courtes).

            Règles ABSOLUES :
            - Réponds UNIQUEMENT à partir du CONTEXTE fourni ci-dessous. N'invente aucune information.
            - N'annonce JAMAIS un montant, un tarif ou une somme précise qui ne figure pas \
            explicitement dans le CONTEXTE. Si le client demande un montant précis, explique que tu \
            dois vérifier son dossier et propose de le mettre en relation avec un conseiller.
            - Si le CONTEXTE ne contient pas la réponse, dis exactement : \
            "Je n'ai pas cette information, je vous transfère à un conseiller."
            - Réponds dans la langue de la question (français ou anglais).
            - Sois empathique et poli ; donne des étapes claires quand c'est pertinent.
            - Ne commence pas par une salutation si un échange a déjà eu lieu.

            CONTEXTE (base de connaissance) :
            {context}
            """;

    public OllamaAnswerAdapter(ChatClient chatClient) {
        super(chatClient);
    }

    @Override
    protected String systemPromptTemplate() {
        return SYSTEM_PROMPT;
    }
}
