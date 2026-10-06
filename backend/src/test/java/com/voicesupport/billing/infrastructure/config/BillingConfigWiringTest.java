package com.voicesupport.billing.infrastructure.config;

import com.voicesupport.billing.domain.port.in.ExplainBillingUseCase;
import com.voicesupport.billing.domain.port.in.ResolveCustomerIdentityUseCase;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.domain.port.out.CustomerDirectoryPort;
import com.voicesupport.billing.domain.port.out.InvoicePdfExtractorPort;
import com.voicesupport.billing.infrastructure.adapter.out.bss.InMemoryBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.EirBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.pdf.FixtureInvoicePdfExtractorAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.pdf.PdfBoxInvoiceExtractorAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

// Config-split wiring regression (TASK-BE-068): BillingAdapterConfig was extracted from BillingConfig
// to stay within the 200-line budget. The split is only safe if the cross-config bean injection still
// resolves at startup — ExplainBillingUseCase (BillingConfig) consumes BssBillingPort
// (BillingAdapterConfig), which in turn consumes billingBssProperties (BillingConfig). mvn test does
// not boot the full context (no @SpringBootTest), so this ApplicationContextRunner slice loads the two
// configs together and asserts every moved/consuming bean resolves. Defaults keep source=mock /
// pdf=fixture / identity=mock, so no network, DB or real PDF is touched.
@DisplayName("BillingConfig / BillingAdapterConfig split wiring (TASK-BE-068)")
class BillingConfigWiringTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(BillingConfig.class, BillingAdapterConfig.class, TelemetrySupport.class);

    @Test
    @DisplayName("both configs load together and every billing bean resolves (default mock mode)")
    void splitConfigsWireTogether() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            // Beans that stayed in BillingConfig.
            assertThat(context).hasSingleBean(BillingBssProperties.class);
            assertThat(context).hasSingleBean(ExplainBillingUseCase.class);
            assertThat(context).hasSingleBean(ResolveCustomerIdentityUseCase.class);
            // Beans moved to BillingAdapterConfig.
            assertThat(context).hasSingleBean(BssBillingPort.class);
            assertThat(context).hasSingleBean(InvoicePdfExtractorPort.class);
            assertThat(context).hasSingleBean(CustomerDirectoryPort.class);
            // Default selection resolves to the mock/fixture adapters (no network, no DB).
            assertThat(context).getBean(BssBillingPort.class).isInstanceOf(InMemoryBssBillingAdapter.class);
            assertThat(context).getBean(InvoicePdfExtractorPort.class)
                    .isInstanceOf(FixtureInvoicePdfExtractorAdapter.class);
        });
    }

    @Test
    @DisplayName("source=eir / pdf=pdfbox selection still wires across the split")
    void eirAndPdfBoxSelectionWiresAcrossSplit() {
        runner.withPropertyValues(
                        "voice-support.billing.bss.source=eir",
                        "voice-support.billing.pdf.source=pdfbox")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).getBean(BssBillingPort.class).isInstanceOf(EirBssBillingAdapter.class);
                    assertThat(context).getBean(InvoicePdfExtractorPort.class)
                            .isInstanceOf(PdfBoxInvoiceExtractorAdapter.class);
                });
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
