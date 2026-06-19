package com.voicesupport.infrastructure.config;

import com.voicesupport.domain.port.in.AskQuestionUseCase;
import com.voicesupport.domain.port.out.SpeechToTextPort;
import com.voicesupport.domain.port.out.TextToSpeechPort;
import com.voicesupport.infrastructure.adapter.in.twilio.TwilioMediaStreamHandler;
import com.voicesupport.infrastructure.adapter.in.websocket.VoiceWebSocketHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final SpeechToTextPort sttPort;
    private final TextToSpeechPort ttsPort;
    private final AskQuestionUseCase askQuestionUseCase;

    public WebSocketConfig(SpeechToTextPort sttPort, TextToSpeechPort ttsPort,
                           AskQuestionUseCase askQuestionUseCase) {
        this.sttPort = sttPort;
        this.ttsPort = ttsPort;
        this.askQuestionUseCase = askQuestionUseCase;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(new VoiceWebSocketHandler(sttPort, ttsPort, askQuestionUseCase), "/ws/voice")
                .setAllowedOrigins("*");
        registry.addHandler(new TwilioMediaStreamHandler(sttPort, ttsPort, askQuestionUseCase), "/ws/twilio")
                .setAllowedOrigins("*");
    }
}
