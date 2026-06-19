package com.voicesupport.infrastructure.adapter.in.websocket;

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

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class VoiceWebSocketHandler extends AbstractWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(VoiceWebSocketHandler.class);

    private final SpeechToTextPort sttPort;
    private final TextToSpeechPort ttsPort;
    private final AskQuestionUseCase askQuestionUseCase;
    private final Map<String, ByteArrayOutputStream> audioBuffers = new ConcurrentHashMap<>();

    public VoiceWebSocketHandler(SpeechToTextPort sttPort, TextToSpeechPort ttsPort,
                                  AskQuestionUseCase askQuestionUseCase) {
        this.sttPort = sttPort;
        this.ttsPort = ttsPort;
        this.askQuestionUseCase = askQuestionUseCase;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        log.info("Voice WebSocket connected: {}", session.getId());
        audioBuffers.put(session.getId(), new ByteArrayOutputStream());
    }

    @Override
    protected void handleBinaryMessage(WebSocketSession session, BinaryMessage message) throws IOException {
        ByteArrayOutputStream buffer = audioBuffers.get(session.getId());
        if (buffer != null) {
            buffer.write(message.getPayload().array());
        }
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws IOException {
        String payload = message.getPayload();

        if ("END_OF_SPEECH".equals(payload)) {
            processAudio(session);
        } else if ("CANCEL".equals(payload)) {
            audioBuffers.put(session.getId(), new ByteArrayOutputStream());
        }
    }

    private void processAudio(WebSocketSession session) throws IOException {
        ByteArrayOutputStream buffer = audioBuffers.get(session.getId());
        if (buffer == null || buffer.size() == 0) {
            session.sendMessage(new TextMessage("{\"error\":\"no_audio\"}"));
            return;
        }

        byte[] audioData = buffer.toByteArray();
        audioBuffers.put(session.getId(), new ByteArrayOutputStream());

        String transcription = sttPort.transcribe(audioData, "wav");
        if (transcription.isBlank()) {
            session.sendMessage(new TextMessage("{\"error\":\"transcription_empty\"}"));
            return;
        }

        session.sendMessage(new TextMessage(
                "{\"type\":\"transcription\",\"text\":\"" + escapeJson(transcription) + "\"}"));

        ConversationResponse response = askQuestionUseCase.ask(session.getId(), transcription);

        session.sendMessage(new TextMessage(
                "{\"type\":\"answer\",\"text\":\"" + escapeJson(response.answer()) + "\"}"));

        byte[] audio = ttsPort.synthesize(response.answer(), "fr");
        if (audio.length > 0) {
            session.sendMessage(new BinaryMessage(audio));
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        log.info("Voice WebSocket disconnected: {}", session.getId());
        audioBuffers.remove(session.getId());
    }

    private String escapeJson(String text) {
        return text.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r");
    }
}
