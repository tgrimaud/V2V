package com.voicesupport.infrastructure.config;

import com.voicesupport.domain.port.out.SpeechToTextPort;
import com.voicesupport.domain.port.out.TextToSpeechPort;
import com.voicesupport.infrastructure.adapter.out.stt.DeepgramSttAdapter;
import com.voicesupport.infrastructure.adapter.out.tts.PiperTtsAdapter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class VoiceConfig {

    @Bean
    public SpeechToTextPort speechToTextPort(
            @Value("${voice-support.stt.deepgram.api-key:}") String apiKey) {
        return new DeepgramSttAdapter(apiKey);
    }

    @Bean
    public TextToSpeechPort textToSpeechPort(
            @Value("${voice-support.tts.piper.host:localhost}") String host,
            @Value("${voice-support.tts.piper.port:10200}") int port) {
        return new PiperTtsAdapter(host, port);
    }
}
