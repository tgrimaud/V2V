package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.TokenStream;

public interface ConverseStreamUseCase {

    TokenStream converseStream(String transcript, String conversationId);
}
