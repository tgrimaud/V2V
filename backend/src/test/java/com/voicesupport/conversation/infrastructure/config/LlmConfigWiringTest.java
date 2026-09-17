package com.voicesupport.conversation.infrastructure.config;

import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.StreamingAnswerGeneratorPort;
import com.voicesupport.conversation.infrastructure.adapter.out.llm.MistralAnswerAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.llm.OllamaAnswerAdapter;
import com.voicesupport.conversation.infrastructure.adapter.out.llm.OpenAiAnswerAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

// Provider-selection wiring regression (TASK-BE-052). Asserts the @ConditionalOnProperty beans in
// LlmConfig activate the correct adapter per voice-support.llm.provider, that an unset property
// defaults to OpenAI (ADR-0051), and that an unknown provider fails startup fast (validateProvider).
// ApplicationContextRunner keeps this a lightweight context slice: the model builders construct API
// clients but make no network call, so no live provider or DB is needed.
@DisplayName("LlmConfig provider selection wiring (DEC-011 / ADR-0051)")
class LlmConfigWiringTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(LlmConfig.class, TelemetrySupport.class);

    @Test
    @DisplayName("provider=openai activates only the OpenAI adapter (both ports resolve to it)")
    void openaiProviderActivatesOpenAiAdapter() {
        runner.withPropertyValues("voice-support.llm.provider=openai").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(OpenAiAnswerAdapter.class);
            assertThat(context).doesNotHaveBean(MistralAnswerAdapter.class);
            assertThat(context).doesNotHaveBean(OllamaAnswerAdapter.class);
            assertThat(context).getBean(AnswerGeneratorPort.class).isInstanceOf(OpenAiAnswerAdapter.class);
            assertThat(context).getBean(StreamingAnswerGeneratorPort.class).isInstanceOf(OpenAiAnswerAdapter.class);
        });
    }

    @Test
    @DisplayName("provider=mistral-api activates only the Mistral adapter")
    void mistralProviderActivatesMistralAdapter() {
        runner.withPropertyValues("voice-support.llm.provider=mistral-api").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(MistralAnswerAdapter.class);
            assertThat(context).doesNotHaveBean(OpenAiAnswerAdapter.class);
            assertThat(context).doesNotHaveBean(OllamaAnswerAdapter.class);
            assertThat(context).getBean(AnswerGeneratorPort.class).isInstanceOf(MistralAnswerAdapter.class);
        });
    }

    @Test
    @DisplayName("provider=ollama activates only the Ollama adapter")
    void ollamaProviderActivatesOllamaAdapter() {
        runner.withPropertyValues("voice-support.llm.provider=ollama").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(OllamaAnswerAdapter.class);
            assertThat(context).doesNotHaveBean(OpenAiAnswerAdapter.class);
            assertThat(context).doesNotHaveBean(MistralAnswerAdapter.class);
            assertThat(context).getBean(AnswerGeneratorPort.class).isInstanceOf(OllamaAnswerAdapter.class);
        });
    }

    @Test
    @DisplayName("unset provider defaults to OpenAI (matchIfMissing, ADR-0051)")
    void unsetProviderDefaultsToOpenAi() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(OpenAiAnswerAdapter.class);
            assertThat(context).getBean(AnswerGeneratorPort.class).isInstanceOf(OpenAiAnswerAdapter.class);
        });
    }

    @Test
    @DisplayName("unknown provider fails startup fast (validateProvider)")
    void unknownProviderFailsStartup() {
        runner.withPropertyValues("voice-support.llm.provider=bogus").run(context ->
                assertThat(context).hasFailed());
    }

    @Configuration
    static class TelemetrySupport {
        @Bean
        MeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        BackendTelemetry backendTelemetry(MeterRegistry registry) {
            return new BackendTelemetry(registry);
        }
    }
}
