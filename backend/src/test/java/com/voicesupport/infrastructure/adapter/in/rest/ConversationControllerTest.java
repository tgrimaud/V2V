package com.voicesupport.infrastructure.adapter.in.rest;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.port.in.AskQuestionUseCase;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ConversationControllerTest {

    @Test
    void ask_uses_default_conversation_id_when_request_has_none() {
        // GIVEN
        RecordingAskQuestionUseCase useCase = new RecordingAskQuestionUseCase();
        ConversationController controller = new ConversationController(useCase);

        // WHEN
        ConversationController.AskResponse response = controller.ask(
                new ConversationController.AskRequest("Why?", null)).getBody();

        // THEN
        assertEquals("default", useCase.conversationId);
        assertEquals("default", response.conversationId());
        assertEquals("billing", response.agentId());
        assertEquals(1, response.citations().size());
    }

    @Test
    void ask_preserves_requested_conversation_id() {
        // GIVEN
        RecordingAskQuestionUseCase useCase = new RecordingAskQuestionUseCase();
        ConversationController controller = new ConversationController(useCase);

        // WHEN
        ConversationController.AskResponse response = controller.ask(
                new ConversationController.AskRequest("Why?", "conv-1")).getBody();

        // THEN
        assertEquals("conv-1", useCase.conversationId);
        assertEquals("conv-1", response.conversationId());
    }

    static class RecordingAskQuestionUseCase implements AskQuestionUseCase {
        String conversationId;

        @Override
        public ConversationResponse ask(String conversationId, String question) {
            this.conversationId = conversationId;
            return new ConversationResponse("answer", citations(), "billing", "Billing", false);
        }

        private List<Citation> citations() {
            return List.of(new Citation("kb", "billing", "text", 0.9));
        }
    }
}
