package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffCommand;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import com.voicesupport.conversation.domain.port.in.FetchEscalationHandoffUseCase;
import com.voicesupport.conversation.domain.port.in.PrepareEscalationHandoffUseCase;
import com.voicesupport.conversation.domain.port.out.EscalationHandoffPort;
import com.voicesupport.conversation.domain.service.EscalationHandoffFactory;
import com.voicesupport.shared.observability.BackendTelemetry;

import java.time.Clock;
import java.util.Optional;

// Escalation hand-off transport (TASK-BE-036 / DEC-013). `prepare` stamps + stores the audited
// payload and returns ONLY the by-reference token (handoff_id + non-PII routing metadata) that the
// channel may carry; `fetch` serves the full payload back on the access-controlled endpoint. Both
// emit privacy-safe telemetry (reason_code + handoff_id, never the summary / last user message).
public class EscalationHandoffService implements PrepareEscalationHandoffUseCase, FetchEscalationHandoffUseCase {

    private static final String REASON_NONE = "n/a";

    private final EscalationHandoffFactory factory;
    private final EscalationHandoffPort store;
    private final Clock clock;
    private final BackendTelemetry telemetry;

    public EscalationHandoffService(
            EscalationHandoffFactory factory,
            EscalationHandoffPort store,
            Clock clock,
            BackendTelemetry telemetry) {
        this.factory = factory;
        this.store = store;
        this.clock = clock;
        this.telemetry = telemetry;
    }

    @Override
    public EscalationHandoffReference prepare(EscalationHandoffCommand command) {
        EscalationHandoff handoff = factory.build(command, clock.instant());
        HandoffId id = store.store(handoff);
        telemetry.recordEscalationHandoff("created", command.reason().code(), id.value());
        return EscalationHandoffReference.of(id, command.reason());
    }

    @Override
    public Optional<EscalationHandoff> fetch(HandoffId handoffId) {
        Optional<EscalationHandoff> found = store.findById(handoffId);
        String outcome = found.isPresent() ? "fetched" : "not_found";
        String reasonCode = found.map(EscalationHandoff::reasonCode).orElse(REASON_NONE);
        telemetry.recordEscalationHandoff(outcome, reasonCode, handoffId.value());
        return found;
    }
}
