package com.voicesupport.infrastructure.adapter.in.rest;

import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.port.in.AskQuestionUseCase;
import com.voicesupport.domain.port.out.SpeechToTextPort;
import com.voicesupport.domain.port.out.TextToSpeechPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.Map;

@RestController
@RequestMapping("/api/voice")
public class VoiceController {

    private final SpeechToTextPort sttPort;
    private final TextToSpeechPort ttsPort;
    private final AskQuestionUseCase askQuestionUseCase;

    public VoiceController(SpeechToTextPort sttPort, TextToSpeechPort ttsPort,
                           AskQuestionUseCase askQuestionUseCase) {
        this.sttPort = sttPort;
        this.ttsPort = ttsPort;
        this.askQuestionUseCase = askQuestionUseCase;
    }

    @PostMapping("/transcribe")
    public ResponseEntity<Map<String, String>> transcribe(
            @RequestParam("audio") MultipartFile audioFile) throws IOException {

        String transcript = sttPort.transcribe(audioFile.getBytes(), "wav");
        return ResponseEntity.ok(Map.of("transcript", transcript));
    }

    @PostMapping("/synthesize")
    public ResponseEntity<byte[]> synthesize(@RequestBody Map<String, String> request) {
        String text = request.getOrDefault("text", "");
        String language = request.getOrDefault("language", "fr");

        byte[] audio = ttsPort.synthesize(text, language);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
        headers.set("Content-Disposition", "attachment; filename=\"response.wav\"");

        return ResponseEntity.ok().headers(headers).body(audio);
    }

    @PostMapping("/ask")
    public ResponseEntity<byte[]> askWithVoice(
            @RequestParam("audio") MultipartFile audioFile,
            @RequestParam(value = "conversation_id", defaultValue = "voice-rest") String conversationId
    ) throws IOException {

        String transcript = sttPort.transcribe(audioFile.getBytes(), "wav");
        if (transcript.isBlank()) {
            return ResponseEntity.badRequest().body(new byte[0]);
        }

        ConversationResponse response = askQuestionUseCase.ask(conversationId, transcript);
        byte[] audio = ttsPort.synthesize(response.answer(), "fr");

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
        headers.set("X-Transcript", transcript);
        headers.set("X-Answer", response.answer().substring(0, Math.min(200, response.answer().length())));

        return ResponseEntity.ok().headers(headers).body(audio);
    }
}
