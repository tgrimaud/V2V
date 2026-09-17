package com.voicesupport.conversation.infrastructure.config;

import com.voicesupport.conversation.application.service.EscalationHandoffService;
import com.voicesupport.conversation.domain.port.out.EscalationHandoffPort;
import com.voicesupport.conversation.domain.service.EscalationHandoffFactory;
import com.voicesupport.conversation.infrastructure.adapter.out.handoff.InMemoryEscalationHandoffAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;

// Escalation hand-off wiring (TASK-BE-036, DEC-013 / ADR-0040), extracted from ConversationConfig
// to keep each configuration class within the 200-line budget (cohesive by concern). Spring wires
// these beans by type into ConverseUseCase / the REST layer regardless of the declaring class.
@Configuration
public class EscalationHandoffConfig {

    // Escalation hand-off transport store: the audited EscalationHandoff payload (incl. PII) stays
    // backend-owned in a process-local bounded LRU; only the minted handoff_id + non-PII routing
    // metadata cross the channel. A shared store (Redis/DB) can replace this behind
    // EscalationHandoffPort for multi-node without touching the domain.
    @Bean
    public EscalationHandoffPort escalationHandoffPort(
            @Value("${voice-support.conversation.handoff.max-handoffs:100000}") int maxHandoffs) {
        return new InMemoryEscalationHandoffAdapter(maxHandoffs);
    }

    @Bean
    public EscalationHandoffFactory escalationHandoffFactory() {
        return new EscalationHandoffFactory();
    }

    // Single service implementing both the prepare (store + reference) and fetch (by-reference)
    // use cases; Spring injects it wherever PrepareEscalationHandoffUseCase or
    // FetchEscalationHandoffUseCase is required. System UTC clock stamps created_at (ADR-0019).
    @Bean
    public EscalationHandoffService escalationHandoffService(
            EscalationHandoffFactory escalationHandoffFactory,
            EscalationHandoffPort escalationHandoffPort,
            BackendTelemetry backendTelemetry) {
        return new EscalationHandoffService(
                escalationHandoffFactory, escalationHandoffPort, Clock.systemUTC(), backendTelemetry);
    }
}
