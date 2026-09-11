package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;

// Inbound use case for the dedicated billing-explanation endpoint (TASK-BE-045, ADR-0051 D3c):
// resolve the answer language, obtain the deterministic grounded explanation through the billing
// seam, then either rephrase it via the LLM under the output guardrail (DEC-002) or voice a safe
// operational/hand-off message. Escalation is decided by the backend (ADR-0019), never the channel.
public interface AnswerBillingQuestionUseCase {

    GeneratedAnswer answer(BillingExplanationRequest request);
}
