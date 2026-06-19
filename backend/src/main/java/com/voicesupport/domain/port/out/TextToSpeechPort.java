package com.voicesupport.domain.port.out;

public interface TextToSpeechPort {

    byte[] synthesize(String text, String language);
}
