package com.voicesupport.infrastructure.adapter.out.stt;

import com.voicesupport.domain.port.out.SpeechToTextPort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.Map;

public class DeepgramSttAdapter implements SpeechToTextPort {

    private static final Logger log = LoggerFactory.getLogger(DeepgramSttAdapter.class);
    private static final String DEEPGRAM_URL = "https://api.deepgram.com/v1/listen";

    private final WebClient webClient;

    public DeepgramSttAdapter(String apiKey) {
        this.webClient = WebClient.builder()
                .baseUrl(DEEPGRAM_URL)
                .defaultHeader("Authorization", "Token " + apiKey)
                .build();
    }

    @Override
    public String transcribe(byte[] audioData, String format) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> response = webClient.post()
                    .uri(uriBuilder -> uriBuilder
                            .queryParam("model", "nova-2")
                            .queryParam("language", "fr")
                            .queryParam("smart_format", "true")
                            .build())
                    .contentType(MediaType.APPLICATION_OCTET_STREAM)
                    .bodyValue(audioData)
                    .retrieve()
                    .bodyToMono(Map.class)
                    .block();

            return extractTranscript(response);
        } catch (Exception e) {
            log.error("Deepgram transcription failed: {}", e.getMessage());
            return "";
        }
    }

    @SuppressWarnings("unchecked")
    private String extractTranscript(Map<String, Object> response) {
        if (response == null) return "";
        Map<String, Object> results = (Map<String, Object>) response.get("results");
        if (results == null) return "";
        var channels = (java.util.List<Map<String, Object>>) results.get("channels");
        if (channels == null || channels.isEmpty()) return "";
        var alternatives = (java.util.List<Map<String, Object>>) channels.get(0).get("alternatives");
        if (alternatives == null || alternatives.isEmpty()) return "";
        return (String) alternatives.get(0).getOrDefault("transcript", "");
    }
}
