package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.shared.config.JacksonConfig;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.CorrelationId;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Exercises the ADR-0013 SSE contract as served: chunk events per safe sentence, a terminal done
// event, and the correlation-id echo. Uses an inline executor so the streamed body is fully
// written before assertions (no api-key configured -> open pilot host).
@WebMvcTest(ConverseStreamController.class)
@Import(JacksonConfig.class)
@DisplayName("ConverseStreamController SSE contract (open)")
class ConverseStreamControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        ConverseStreamUseCase converseStreamUseCase() {
            return (transcript, conversationId) -> streamOf("Bonjour.", "Comment puis-je aider ?");
        }

        @Bean
        BackendTelemetry backendTelemetry() {
            return new BackendTelemetry(new SimpleMeterRegistry());
        }

        @Bean
        ExecutorService sseStreamExecutor() {
            return new InlineExecutorService();
        }

        private static TokenStream streamOf(String first, String second) {
            return onChunk -> {
                onChunk.accept(first);
                onChunk.accept(second);
                return GeneratedAnswer.grounded(first + " " + second, 0.9);
            };
        }
    }

    @Test
    @DisplayName("streams a chunk event per sentence and a terminal done event")
    void streamsChunksThenDone() throws Exception {
        String body = dispatchBody("{\"transcript\":\"Bonjour\",\"conversation_id\":\"c1\",\"channel\":\"web\"}");

        assertTrue(body.contains("event:chunk"), body);
        assertTrue(body.contains("Bonjour."), body);
        assertTrue(body.contains("event:done"), body);
        assertTrue(body.contains("\"grounded\":true"), body);
    }

    @Test
    @DisplayName("a blank transcript streams a safe listen prompt")
    void blankTranscriptStreamsListenPrompt() throws Exception {
        String body = dispatchBody("{\"transcript\":\"   \",\"conversation_id\":\"c1\"}");

        assertTrue(body.contains("Je vous écoute, posez-moi votre question."), body);
        assertTrue(body.contains("event:done"), body);
    }

    @Test
    @DisplayName("echoes the runtime correlation id (from the body) on the response header")
    void echoesCorrelationIdHeader() throws Exception {
        MvcResult started = mockMvc.perform(post("/api/conversation/converse-stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"transcript\":\"Bonjour\",\"correlation_id\":\"corr-42\",\"channel\":\"web\"}"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(header().string(CorrelationId.HEADER, "corr-42"));
    }

    private String dispatchBody(String json) throws Exception {
        MvcResult started = mockMvc.perform(post("/api/conversation/converse-stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(request().asyncStarted())
                .andReturn();
        return mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
    }

    // Runs submitted tasks on the calling thread so the SSE body is fully buffered before dispatch.
    static class InlineExecutorService extends AbstractExecutorService {
        @Override
        public void execute(Runnable command) {
            command.run();
        }

        @Override
        public void shutdown() {
        }

        @Override
        public List<Runnable> shutdownNow() {
            return List.of();
        }

        @Override
        public boolean isShutdown() {
            return true;
        }

        @Override
        public boolean isTerminated() {
            return true;
        }

        @Override
        public boolean awaitTermination(long timeout, TimeUnit unit) {
            return true;
        }
    }
}
