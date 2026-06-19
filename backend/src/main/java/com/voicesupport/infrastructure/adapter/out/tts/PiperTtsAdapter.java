package com.voicesupport.infrastructure.adapter.out.tts;

import com.voicesupport.domain.port.out.TextToSpeechPort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class PiperTtsAdapter implements TextToSpeechPort {

    private static final Logger log = LoggerFactory.getLogger(PiperTtsAdapter.class);

    private final String host;
    private final int port;

    public PiperTtsAdapter(String host, int port) {
        this.host = host;
        this.port = port;
    }

    @Override
    public byte[] synthesize(String text, String language) {
        try (Socket socket = new Socket(host, port);
             DataOutputStream out = new DataOutputStream(socket.getOutputStream());
             DataInputStream in = new DataInputStream(socket.getInputStream())) {

            byte[] textBytes = text.getBytes(StandardCharsets.UTF_8);
            out.writeInt(textBytes.length);
            out.write(textBytes);
            out.flush();

            int audioLength = in.readInt();
            byte[] audio = new byte[audioLength];
            in.readFully(audio);

            return audio;
        } catch (IOException e) {
            log.error("Piper TTS synthesis failed: {}", e.getMessage());
            return new byte[0];
        }
    }
}
