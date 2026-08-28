package com.voicesupport.conversation.domain.model.valueobject;

import java.util.Locale;

// How a channel expects the shared backend's answer to be delivered (TASK-BE-037 / ADR-0009).
// V1 channels are voice-first (Genesys Audio Connector, WebRTC); text covers chat/WhatsApp. Part
// of the normalized channel envelope so routing/escalation stay channel-agnostic.
public enum ReplyMode {

    VOICE("voice"),
    TEXT("text");

    private final String code;

    ReplyMode(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    // Maps a wire code to a mode. Null/blank defaults to VOICE (the V1 voice-first default); an
    // unrecognized non-blank code is a caller error and is rejected (mapped to 400 upstream). The
    // rejected code is never echoed in the message to avoid log injection from client input.
    public static ReplyMode fromCode(String code) {
        if (code == null || code.isBlank()) {
            return VOICE;
        }
        String normalized = code.trim().toLowerCase(Locale.ROOT);
        for (ReplyMode mode : values()) {
            if (mode.code.equals(normalized)) {
                return mode;
            }
        }
        throw new IllegalArgumentException("unsupported reply_mode");
    }
}
