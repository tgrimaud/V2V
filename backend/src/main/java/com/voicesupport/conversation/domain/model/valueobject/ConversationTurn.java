package com.voicesupport.conversation.domain.model.valueobject;

// One completed exchange in a conversation: what the customer said and what the assistant
// replied. Used as short conversation memory (TASK-BE-006) to give the LLM prior context.
public record ConversationTurn(String userText, String assistantText) {
}
