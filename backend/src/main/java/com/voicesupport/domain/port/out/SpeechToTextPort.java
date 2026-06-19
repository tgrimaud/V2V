package com.voicesupport.domain.port.out;

public interface SpeechToTextPort {

    String transcribe(byte[] audioData, String format);
}
