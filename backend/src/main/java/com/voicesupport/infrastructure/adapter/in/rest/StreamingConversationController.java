package com.voicesupport.infrastructure.adapter.in.rest;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.ConversationStreamResponse;
import com.voicesupport.domain.port.in.AskQuestionStreamingUseCase;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@RestController
@RequestMapping("/api/conversation")
public class StreamingConversationController {

    private static final Logger log = LoggerFactory.getLogger(StreamingConversationController.class);

    private final AskQuestionStreamingUseCase streamingUseCase;
    private final ObjectMapper objectMapper;
    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();

    public StreamingConversationController(
            @Qualifier("askQuestionStreamingUseCase") AskQuestionStreamingUseCase streamingUseCase,
            ObjectMapper objectMapper) {
        this.streamingUseCase = streamingUseCase;
        this.objectMapper = objectMapper;
    }

    @GetMapping(value = "/ask-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter askStream(
            @RequestParam(name = "question") String question,
            @RequestParam(name = "conversation_id", defaultValue = "default") String conversationId) {

        SseEmitter emitter = new SseEmitter(60_000L);
        long startTime = System.currentTimeMillis();
        executor.execute(() -> streamAnswer(emitter, conversationId, question, startTime));
        return emitter;
    }

    @PostMapping("/seed")
    public ResponseEntity<Void> seed(@RequestBody SeedRequest request) {
        String conversationId = request.conversationId() != null ? request.conversationId() : "default";
        streamingUseCase.seedAssistantMessage(conversationId, request.message());
        return ResponseEntity.noContent().build();
    }

    @PreDestroy
    public void shutdown() {
        executor.shutdown();
    }

    public record SeedRequest(String message,
                              @JsonProperty("conversation_id") String conversationId) {}

    private void streamAnswer(SseEmitter emitter, String conversationId, String question, long startTime) {
        try {
            ConversationStreamResponse result = streamingUseCase.askStream(conversationId, question);
            if (result.escalated()) {
                sendSingleShot(emitter, result, conversationId, false);
            } else if (result.guardrailBlocked()) {
                sendSingleShot(emitter, result, conversationId, true);
            } else {
                streamTokens(emitter, result, conversationId, question, startTime);
            }
        } catch (Exception e) {
            failStream(emitter, e);
        }
    }

    private void sendSingleShot(SseEmitter emitter, ConversationStreamResponse result,
                                String conversationId, boolean guardrailBlocked) {
        String text = firstToken(result);
        sendStart(emitter, result.agentId(), result.agentName(), guardrailBlocked);
        sendChunk(emitter, text);
        sendDone(emitter, text, result.citations(), conversationId, result.agentId(), result.agentName());
        emitter.complete();
    }

    private void streamTokens(SseEmitter emitter, ConversationStreamResponse result,
                              String conversationId, String question, long startTime) {
        StringBuilder fullAnswer = new StringBuilder();
        sendStart(emitter, result.agentId(), result.agentName(), result.guardrailBlocked());
        try {
            for (String token : result.tokens()) {
                fullAnswer.append(token);
                sendChunk(emitter, token);
            }
            completeStream(emitter, result, conversationId, question, fullAnswer, startTime);
        } catch (RuntimeException e) {
            failStream(emitter, e);
        }
    }

    private void completeStream(SseEmitter emitter, ConversationStreamResponse result, String conversationId,
                                String question, StringBuilder fullAnswer, long startTime) {
        String answer = fullAnswer.toString();
        streamingUseCase.recordCompletion(conversationId, question, answer, result.citations(), startTime);
        sendDone(emitter, answer, result.citations(), conversationId, result.agentId(), result.agentName());
        emitter.complete();
    }

    private String firstToken(ConversationStreamResponse result) {
        var iterator = result.tokens().iterator();
        return iterator.hasNext() ? iterator.next() : "";
    }

    private void failStream(SseEmitter emitter, Throwable error) {
        String correlationId = UUID.randomUUID().toString();
        log.error("[{}] Streaming conversation failed", correlationId, error);
        sendError(emitter, correlationId);
        emitter.completeWithError(error);
    }

    private void sendStart(SseEmitter emitter, String agentId, String agentName, boolean guardrailBlocked) {
        Map<String, Object> data = new LinkedHashMap<>();
        putIfPresent(data, "agentId", agentId);
        putIfPresent(data, "agentName", agentName);
        data.put("guardrailBlocked", guardrailBlocked);
        emit(emitter, "start", data);
    }

    private void sendChunk(SseEmitter emitter, String text) {
        emit(emitter, "chunk", Map.of("text", text == null ? "" : text));
    }

    private void sendDone(SseEmitter emitter, String fullAnswer, List<Citation> citations,
                          String conversationId, String agentId, String agentName) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("answer", fullAnswer);
        data.put("citations", citations.stream().map(this::toCitationMap).toList());
        data.put("conversationId", conversationId);
        putIfPresent(data, "agentId", agentId);
        putIfPresent(data, "agentName", agentName);
        emit(emitter, "done", data);
    }

    private void sendError(SseEmitter emitter, String correlationId) {
        Map<String, Object> data = Map.of(
                "code", "ERR_STREAM_FAILED",
                "message", "An error occurred while generating the answer.",
                "correlation_id", correlationId);
        emit(emitter, "error", data);
    }

    private Map<String, Object> toCitationMap(Citation c) {
        return Map.of(
                "source", c.source(),
                "section", c.section(),
                "relevantText", c.relevantText(),
                "score", c.score());
    }

    private void putIfPresent(Map<String, Object> data, String key, String value) {
        if (value != null) {
            data.put(key, value);
        }
    }

    private void emit(SseEmitter emitter, String event, Map<String, Object> data) {
        try {
            emitter.send(SseEmitter.event().name(event).data(serialize(data)));
        } catch (IOException ignored) {
            // Client already disconnected — nothing actionable.
        }
    }

    private String serialize(Map<String, Object> data) {
        try {
            return objectMapper.writeValueAsString(data);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}
