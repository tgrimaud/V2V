package com.voicesupport.infrastructure.adapter.in.twilio;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/twilio")
public class TwilioWebhookController {

    @PostMapping(value = "/voice", produces = MediaType.APPLICATION_XML_VALUE)
    public String handleIncomingCall(HttpServletRequest request) {
        String host = request.getHeader("X-Forwarded-Host");
        if (host == null) {
            host = request.getServerName() + ":" + request.getServerPort();
        }
        String wsScheme = request.isSecure() ? "wss" : "ws";

        return """
                <?xml version="1.0" encoding="UTF-8"?>
                <Response>
                    <Say language="fr-FR">Bienvenue sur le support technique. Comment puis-je vous aider ?</Say>
                    <Connect>
                        <Stream url="%s://%s/ws/twilio" />
                    </Connect>
                </Response>
                """.formatted(wsScheme, host);
    }
}
