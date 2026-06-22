package com.voicesupport.infrastructure.adapter.in.rest;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.service.ConversationOrchestrator;
import com.voicesupport.domain.service.ConversationOrchestrator.StreamingResult;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@RestController
@RequestMapping("/api/conversation")
public class StreamingConversationController {

    private final ConversationOrchestrator orchestrator;
    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();

    public StreamingConversationController(ConversationOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @GetMapping(value = "/ask-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter askStream(
            @RequestParam(name = "question") String question,
            @RequestParam(name = "conversation_id", defaultValue = "default") String conversationId) {

        SseEmitter emitter = new SseEmitter(60_000L);
        long startTime = System.currentTimeMillis();

        executor.execute(() -> {
            try {
                StreamingResult result = orchestrator.askStream(conversationId, question);
                List<Citation> citations = result.citations();

                if (result.escalated()) {
                    String escalationText = result.tokens().blockFirst();
                    sendStart(emitter, result.agentId(), result.agentName(), false);
                    sendChunk(emitter, escalationText);
                    sendDone(emitter, escalationText, citations, conversationId, result.agentId(), result.agentName());
                    emitter.complete();
                    return;
                }

                if (result.guardrailBlocked()) {
                    String blockedText = result.tokens().blockFirst();
                    sendStart(emitter, result.agentId(), result.agentName(), true);
                    sendChunk(emitter, blockedText);
                    sendDone(emitter, blockedText, citations, conversationId, result.agentId(), result.agentName());
                    emitter.complete();
                    return;
                }

                StringBuilder fullAnswer = new StringBuilder();

                sendStart(emitter, result.agentId(), result.agentName(), result.guardrailBlocked());

                result.tokens()
                        .doOnNext(token -> {
                            fullAnswer.append(token);
                            sendChunk(emitter, token);
                        })
                        .doOnComplete(() -> {
                            String answer = fullAnswer.toString();
                            orchestrator.recordCompletion(
                                    conversationId, question, answer, citations, startTime);
                            sendDone(emitter, answer, citations, conversationId, result.agentId(), result.agentName());
                            emitter.complete();
                        })
                        .doOnError(error -> {
                            sendError(emitter, error.getMessage());
                            emitter.completeWithError(error);
                        })
                        .subscribe();

            } catch (Exception e) {
                sendError(emitter, e.getMessage());
                emitter.completeWithError(e);
            }
        });

        return emitter;
    }

    private void sendStart(SseEmitter emitter, String agentId, String agentName, boolean guardrailBlocked) {
        try {
            String agentField = agentId != null ? "\"agentId\":\"" + escapeJson(agentId) + "\"," : "";
            String agentNameField = agentName != null ? "\"agentName\":\"" + escapeJson(agentName) + "\"," : "";
            String data = "{" + agentField + agentNameField
                    + "\"guardrailBlocked\":" + guardrailBlocked + "}";
            emitter.send(SseEmitter.event()
                    .name("start")
                    .data(data));
        } catch (IOException e) {
            emitter.completeWithError(e);
        }
    }

    private void sendChunk(SseEmitter emitter, String text) {
        try {
            emitter.send(SseEmitter.event()
                    .name("chunk")
                    .data("{\"text\":\"" + escapeJson(text) + "\"}"));
        } catch (IOException e) {
            emitter.completeWithError(e);
        }
    }

    private void sendDone(SseEmitter emitter, String fullAnswer,
                          List<Citation> citations, String conversationId,
                          String agentId, String agentName) {
        try {
            StringBuilder citationsJson = new StringBuilder("[");
            for (int i = 0; i < citations.size(); i++) {
                Citation c = citations.get(i);
                if (i > 0) citationsJson.append(",");
                citationsJson.append("{\"source\":\"").append(escapeJson(c.source()))
                        .append("\",\"section\":\"").append(escapeJson(c.section()))
                        .append("\",\"relevantText\":\"").append(escapeJson(c.relevantText()))
                        .append("\",\"score\":").append(c.score()).append("}");
            }
            citationsJson.append("]");

            String agentField = agentId != null ? ",\"agentId\":\"" + escapeJson(agentId) + "\"" : "";
            String agentNameField = agentName != null ? ",\"agentName\":\"" + escapeJson(agentName) + "\"" : "";
            String data = "{\"answer\":\"" + escapeJson(fullAnswer)
                    + "\",\"citations\":" + citationsJson
                    + ",\"conversationId\":\"" + escapeJson(conversationId) + "\""
                    + agentField + agentNameField + "}";

            emitter.send(SseEmitter.event()
                    .name("done")
                    .data(data));
        } catch (IOException e) {
            emitter.completeWithError(e);
        }
    }

    private void sendError(SseEmitter emitter, String message) {
        try {
            emitter.send(SseEmitter.event()
                    .name("error")
                    .data("{\"message\":\"" + escapeJson(message) + "\"}"));
        } catch (IOException ignored) {
            // Client already disconnected
        }
    }

    private String escapeJson(String input) {
        if (input == null) return "";
        return input.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
}
