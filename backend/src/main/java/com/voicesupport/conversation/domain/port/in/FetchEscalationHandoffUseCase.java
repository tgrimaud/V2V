package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;

import java.util.Optional;

// Serves the full audited hand-off payload back by reference (TASK-BE-036 / DEC-013). Empty when the
// id is unknown so the caller returns a sanitized not-found error without echoing internal detail.
public interface FetchEscalationHandoffUseCase {

    Optional<EscalationHandoff> fetch(HandoffId handoffId);
}
