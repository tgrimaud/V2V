package com.voicesupport.infrastructure.adapter.in.twilio;

import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.port.in.AskQuestionUseCase;
import com.voicesupport.domain.port.out.SpeechToTextPort;
import com.voicesupport.domain.port.out.TextToSpeechPort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.socket.BinaryMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.AbstractWebSocketHandler;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class TwilioMediaStreamHandler extends AbstractWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(TwilioMediaStreamHandler.class);

    private final SpeechToTextPort sttPort;
    private final TextToSpeechPort ttsPort;
    private final AskQuestionUseCase askQuestionUseCase;
    private final ObjectMapper objectMapper = new ObjectMapper();

    private final Map<String, ByteArrayOutputStream> audioBuffers = new ConcurrentHashMap<>();
    private final Map<String, String> streamSids = new ConcurrentHashMap<>();

    public TwilioMediaStreamHandler(SpeechToTextPort sttPort, TextToSpeechPort ttsPort,
                                     AskQuestionUseCase askQuestionUseCase) {
        this.sttPort = sttPort;
        this.ttsPort = ttsPort;
        this.askQuestionUseCase = askQuestionUseCase;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        log.info("Twilio Media Stream connected: {}", session.getId());
        audioBuffers.put(session.getId(), new ByteArrayOutputStream());
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws IOException {
        JsonNode event = objectMapper.readTree(message.getPayload());
        String eventType = event.path("event").asText();

        switch (eventType) {
            case "connected" -> log.info("Twilio stream connected");
            case "start" -> handleStart(session, event);
            case "media" -> handleMedia(session, event);
            case "mark" -> handleMark(session, event);
            case "stop" -> handleStop(session);
            default -> log.debug("Unknown Twilio event: {}", eventType);
        }
    }

    private void handleStart(WebSocketSession session, JsonNode event) {
        String streamSid = event.path("start").path("streamSid").asText();
        streamSids.put(session.getId(), streamSid);
        log.info("Twilio stream started: {}", streamSid);
    }

    private void handleMedia(WebSocketSession session, JsonNode event) {
        String audioBase64 = event.path("media").path("payload").asText();
        byte[] audioChunk = Base64.getDecoder().decode(audioBase64);

        ByteArrayOutputStream buffer = audioBuffers.get(session.getId());
        if (buffer != null) {
            buffer.write(audioChunk, 0, audioChunk.length);

            // Simple silence detection: process after ~3 seconds of audio (24000 bytes at 8kHz mulaw)
            if (buffer.size() > 24000) {
                processAndRespond(session);
            }
        }
    }

    private void handleMark(WebSocketSession session, JsonNode event) {
        log.debug("Twilio mark received: {}", event.path("mark").path("name").asText());
    }

    private void handleStop(WebSocketSession session) {
        processAndRespond(session);
    }

    private void processAndRespond(WebSocketSession session) {
        ByteArrayOutputStream buffer = audioBuffers.get(session.getId());
        if (buffer == null || buffer.size() == 0) return;

        byte[] audioData = buffer.toByteArray();
        audioBuffers.put(session.getId(), new ByteArrayOutputStream());

        String transcription = sttPort.transcribe(audioData, "mulaw");
        if (transcription.isBlank()) return;

        log.info("Twilio transcription: {}", transcription);

        ConversationResponse response = askQuestionUseCase.ask(session.getId(), transcription);

        byte[] ttsAudio = ttsPort.synthesize(response.answer(), "fr");
        if (ttsAudio.length > 0) {
            sendTwilioAudio(session, ttsAudio);
        }
    }

    private void sendTwilioAudio(WebSocketSession session, byte[] audio) {
        String streamSid = streamSids.get(session.getId());
        if (streamSid == null) return;

        String audioBase64 = Base64.getEncoder().encodeToString(audio);
        String mediaMessage = String.format(
                "{\"event\":\"media\",\"streamSid\":\"%s\",\"media\":{\"payload\":\"%s\"}}",
                streamSid, audioBase64);

        try {
            session.sendMessage(new TextMessage(mediaMessage));

            String markMessage = String.format(
                    "{\"event\":\"mark\",\"streamSid\":\"%s\",\"mark\":{\"name\":\"response_end\"}}",
                    streamSid);
            session.sendMessage(new TextMessage(markMessage));
        } catch (IOException e) {
            log.error("Failed to send audio to Twilio: {}", e.getMessage());
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        log.info("Twilio Media Stream disconnected: {}", session.getId());
        audioBuffers.remove(session.getId());
        streamSids.remove(session.getId());
    }
}
