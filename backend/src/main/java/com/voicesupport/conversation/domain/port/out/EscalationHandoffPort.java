package com.voicesupport.conversation.domain.port.out;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;

import java.util.Optional;

// Backend-owned store for audited escalation hand-offs (TASK-BE-036 / DEC-013 / ADR-0040). `store`
// persists the full payload and mints the opaque handoff_id that becomes the by-reference token;
// `findById` serves the payload back on an access-controlled fetch. The default in-memory adapter
// can be replaced by a shared store (Redis/DB) behind this port for multi-node without touching the
// domain.
public interface EscalationHandoffPort {

    HandoffId store(EscalationHandoff handoff);

    Optional<EscalationHandoff> findById(HandoffId handoffId);
}
