package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.TokenStream;

public interface ConverseStreamUseCase {

    TokenStream converseStream(String transcript, String conversationId);

    // US-042: streaming turn with an explicit forced answer language (UI selector) overriding
    // detection; a null/blank code keeps the current behavior. Default delegates for compatibility.
    default TokenStream converseStream(String transcript, String conversationId, String forcedLanguage) {
        return converseStream(transcript, conversationId);
    }
}
