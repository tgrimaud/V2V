package com.voicesupport.conversation.infrastructure.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.ConversationMemoryPort;
import com.voicesupport.conversation.domain.port.out.DeliveryDeduplicationPort;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.conversation.domain.port.out.StreamingAnswerGeneratorPort;
import com.voicesupport.conversation.domain.service.IdempotentDeliveryGuard;
import com.voicesupport.conversation.fake.FakeAnswerGeneratorPort;
import com.voicesupport.conversation.fake.FakeKnowledgeRetrievalPort;
import com.voicesupport.conversation.fake.FakeStreamingAnswerGeneratorPort;
import com.voicesupport.conversation.infrastructure.adapter.out.idempotency.InMemoryDeliveryDeduplicationAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.InMemoryConversationMemoryAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

// Config-split wiring regression (TASK-BE-068): ConversationMemoryConfig (conversationMemoryPort,
// deliveryDeduplicationPort, idempotentDeliveryGuard) was extracted from ConversationConfig to stay
// within the 200-line budget. The split is only safe if ConversationConfig's converseUseCase /
// converseStreamUseCase still receive the ConversationMemoryPort now defined in the sibling config.
// mvn test does not boot the full context (no @SpringBootTest), so this ApplicationContextRunner slice
// loads both configs together (with fakes for the external ports) and asserts the cross-config beans
// resolve. Default store=memory, so no Redis is required.
@DisplayName("ConversationConfig / ConversationMemoryConfig split wiring (TASK-BE-068)")
class ConversationMemoryConfigWiringTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(ConversationConfig.class, ConversationMemoryConfig.class, PortSupport.class);

    @Test
    @DisplayName("both configs load together and the memory-consuming use-cases resolve (default memory store)")
    void splitConfigsWireTogether() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            // Beans moved to ConversationMemoryConfig.
            assertThat(context).hasSingleBean(ConversationMemoryPort.class);
            assertThat(context).hasSingleBean(DeliveryDeduplicationPort.class);
            assertThat(context).hasSingleBean(IdempotentDeliveryGuard.class);
            // Default store=memory / idempotency = in-memory (no Redis bean needed).
            assertThat(context).getBean(ConversationMemoryPort.class)
                    .isInstanceOf(InMemoryConversationMemoryAdapter.class);
            assertThat(context).getBean(DeliveryDeduplicationPort.class)
                    .isInstanceOf(InMemoryDeliveryDeduplicationAdapter.class);
            // Cross-config consumers in ConversationConfig that inject ConversationMemoryPort.
            assertThat(context).hasSingleBean(ConverseUseCase.class);
            assertThat(context).hasSingleBean(ConverseStreamUseCase.class);
        });
    }

    @Configuration
    static class PortSupport {
        @Bean
        MeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        BackendTelemetry backendTelemetry(MeterRegistry registry) {
            return new BackendTelemetry(registry);
        }

        @Bean
        ObjectMapper objectMapper() {
            return new ObjectMapper();
        }

        @Bean
        KnowledgeRetrievalPort knowledgeRetrievalPort() {
            return new FakeKnowledgeRetrievalPort();
        }

        @Bean
        AnswerGeneratorPort answerGeneratorPort() {
            return new FakeAnswerGeneratorPort();
        }

        @Bean
        StreamingAnswerGeneratorPort streamingAnswerGeneratorPort() {
            return new FakeStreamingAnswerGeneratorPort();
        }
    }
}
