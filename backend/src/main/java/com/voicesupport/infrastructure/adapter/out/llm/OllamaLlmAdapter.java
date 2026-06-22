package com.voicesupport.infrastructure.adapter.out.llm;

import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

public class OllamaLlmAdapter implements LlmPort, LlmStreamingPort {

    private static final Logger log = LoggerFactory.getLogger(OllamaLlmAdapter.class);

    private static final String DEFAULT_SYSTEM_PROMPT = """
            Tu es un agent de support client pour un opérateur Telecom/FAI.
            Tu réponds aux questions des clients de manière claire, concise et professionnelle.
            
            Règles ABSOLUES :
            - Réponds UNIQUEMENT à partir du contexte fourni ci-dessous.
            - Si le contexte ne contient pas la réponse, dis "Je n'ai pas cette information, \
            je vous transfère à un conseiller."
            - Sois empathique et poli.
            - Donne des instructions étape par étape quand c'est pertinent.
            - Réponds en français.
            - INTERDIT : ne commence JAMAIS par "Bonjour", "Hello", "Salut" ou toute autre salutation \
            si l'historique de conversation contient déjà un échange. Va directement au contenu utile.
            - Si c'est le tout premier message (historique vide), tu peux saluer le client.
            
            Contexte de la base de connaissance :
            {context}
            """;

    private final ChatClient chatClient;

    public OllamaLlmAdapter(ChatClient chatClient) {
        this.chatClient = chatClient;
    }

    @Override
    public String generateAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
        return generateAnswer(question, contextChunks, conversationHistory, null);
    }

    @Override
    public String generateAnswer(String question, List<String> contextChunks,
                                  List<String> conversationHistory, String systemPrompt) {
        String context = String.join("\n---\n", contextChunks);
        String prompt = (systemPrompt != null) ? systemPrompt : DEFAULT_SYSTEM_PROMPT;
        String systemMessage = prompt.replace("{context}", context);

        if (!conversationHistory.isEmpty()) {
            systemMessage += "\n\nHistorique de la conversation (ne répète PAS de salutation si un 'Bonjour' apparaît déjà) :\n"
                    + String.join("\n", conversationHistory);
        }

        return chatClient.prompt()
                .system(systemMessage)
                .user(question)
                .call()
                .content();
    }

    @Override
    public Flux<String> streamAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
        return streamAnswer(question, contextChunks, conversationHistory, null);
    }

    @Override
    public Flux<String> streamAnswer(String question, List<String> contextChunks,
                                      List<String> conversationHistory, String systemPrompt) {
        String context = String.join("\n---\n", contextChunks);
        String prompt = (systemPrompt != null) ? systemPrompt : DEFAULT_SYSTEM_PROMPT;
        String systemMessage = prompt.replace("{context}", context);

        if (!conversationHistory.isEmpty()) {
            systemMessage += "\n\nHistorique de la conversation (ne répète PAS de salutation si un 'Bonjour' apparaît déjà) :\n"
                    + String.join("\n", conversationHistory);
        }

        final String finalSystemMessage = systemMessage;
        return Flux.defer(() -> {
            long startNanos = System.nanoTime();
            AtomicBoolean firstToken = new AtomicBoolean(true);
            return chatClient.prompt()
                    .system(finalSystemMessage)
                    .user(question)
                    .stream()
                    .content()
                    .doOnNext(token -> {
                        if (firstToken.compareAndSet(true, false)) {
                            long ms = (System.nanoTime() - startNanos) / 1_000_000;
                            log.info("[LATENCY] step=llm_first_token ms={}", ms);
                        }
                    })
                    .doOnComplete(() -> {
                        long ms = (System.nanoTime() - startNanos) / 1_000_000;
                        log.info("[LATENCY] step=llm_total ms={}", ms);
                    });
        });
    }
}
