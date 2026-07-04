package com.voicesupport.infrastructure.adapter.in.rest;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.ConversationStreamResponse;
import com.voicesupport.domain.model.TokenStream;
import com.voicesupport.domain.port.in.AskQuestionStreamingUseCase;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StreamingConversationControllerTest {

    @Test
    void seed_uses_default_conversation_id_when_request_has_none() {
        // GIVEN
        RecordingStreamingUseCase useCase = new RecordingStreamingUseCase();
        StreamingConversationController controller = new StreamingConversationController(useCase, new ObjectMapper());

        // WHEN
        controller.seed(new StreamingConversationController.SeedRequest("Bonjour", null));

        // THEN
        assertEquals("default", useCase.seedConversationId);
        assertEquals("Bonjour", useCase.seedMessage);
        controller.shutdown();
    }

    @Test
    void ask_stream_invokes_streaming_use_case() throws InterruptedException {
        // GIVEN
        RecordingStreamingUseCase useCase = new RecordingStreamingUseCase();
        StreamingConversationController controller = new StreamingConversationController(useCase, new ObjectMapper());

        // WHEN
        var emitter = controller.askStream("Bonjour", "conv-1");

        // THEN
        assertNotNull(emitter);
        assertTrue(useCase.awaitAsk());
        assertEquals("conv-1", useCase.askConversationId);
        assertEquals("Bonjour", useCase.askQuestion);
        controller.shutdown();
    }

    static class RecordingStreamingUseCase implements AskQuestionStreamingUseCase {
        private final CountDownLatch askCalled = new CountDownLatch(1);
        String askConversationId;
        String askQuestion;
        String seedConversationId;
        String seedMessage;

        @Override
        public ConversationStreamResponse askStream(String conversationId, String question) {
            this.askConversationId = conversationId;
            this.askQuestion = question;
            askCalled.countDown();
            return new ConversationStreamResponse(
                    TokenStream.fromIterable(List.of("answer")),
                    List.of(new Citation("kb", "section", "text", 0.9)),
                    false, false, "support", "Support");
        }

        @Override
        public void seedAssistantMessage(String conversationId, String message) {
            this.seedConversationId = conversationId;
            this.seedMessage = message;
        }

        @Override
        public void recordCompletion(String conversationId, String question,
                                     String fullAnswer, List<Citation> citations, long startTime) {
        }

        @Override
        public String getCurrentAgentId(String conversationId) {
            return "support";
        }

        boolean awaitAsk() throws InterruptedException {
            return askCalled.await(1, TimeUnit.SECONDS);
        }
    }
}
