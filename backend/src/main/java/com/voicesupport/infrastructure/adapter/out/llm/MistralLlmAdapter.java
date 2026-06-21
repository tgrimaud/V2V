package com.voicesupport.infrastructure.adapter.out.llm;

import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import org.springframework.ai.chat.client.ChatClient;
import reactor.core.publisher.Flux;

import java.util.List;

public class MistralLlmAdapter implements LlmPort, LlmStreamingPort {

    private static final String SYSTEM_PROMPT = """
            Tu es un agent de support client pour un opérateur Telecom/FAI.
            Tu réponds aux questions des clients de manière claire, concise et professionnelle.
            
            Règles :
            - Réponds à partir du contexte fourni ci-dessous.
            - Si la question est vague mais concerne un sujet présent dans le contexte, \
            demande des précisions au client (ex: "Pouvez-vous préciser votre problème ?").
            - Si le contexte ne contient VRAIMENT PAS d'information sur le sujet, \
            dis "Je n'ai pas cette information, je vous transfère à un conseiller."
            - Sois empathique et poli.
            - Donne des instructions étape par étape quand c'est pertinent.
            - Réponds dans la langue de la question.
            - Ne répète JAMAIS une salutation (bonjour, hello, etc.) si une a déjà été échangée dans l'historique.
            - Va directement au sujet sans formule d'accueil redondante.
            
            Contexte de la base de connaissance :
            {context}
            """;

    private final ChatClient chatClient;

    public MistralLlmAdapter(ChatClient chatClient) {
        this.chatClient = chatClient;
    }

    @Override
    public String generateAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
        String context = String.join("\n---\n", contextChunks);
        String history = conversationHistory.isEmpty() ? "" :
                "\n\nHistorique de la conversation :\n" + String.join("\n", conversationHistory);

        String systemMessage = SYSTEM_PROMPT.replace("{context}", context);

        return chatClient.prompt()
                .system(systemMessage)
                .user(question + history)
                .call()
                .content();
    }

    @Override
    public Flux<String> streamAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
        String context = String.join("\n---\n", contextChunks);
        String history = conversationHistory.isEmpty() ? "" :
                "\n\nHistorique de la conversation :\n" + String.join("\n", conversationHistory);

        String systemMessage = SYSTEM_PROMPT.replace("{context}", context);

        return chatClient.prompt()
                .system(systemMessage)
                .user(question + history)
                .stream()
                .content();
    }
}
