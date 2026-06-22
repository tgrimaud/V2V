package com.voicesupport.domain.port.out;

import com.voicesupport.domain.model.Conversation;

public interface ConversationStore {

    Conversation load(String conversationId);

    void save(String conversationId, Conversation conversation);
}
