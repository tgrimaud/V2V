package com.voicesupport.conversation.domain.port.out;

import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.BillingGrounding;

// Outbound seam from the answer engine to the billing context (TASK-BE-045, ADR-0051): given a
// billing-explanation turn, return the deterministic, grounded result the LLM may rephrase (DEC-002)
// or a safe hand-off. Keeps the conversation domain free of billing types; the in-proc adapter maps
// across the context boundary (mirrors the knowledge retrieval seam, ADR-0027).
public interface BillingExplanationPort {

    BillingGrounding explain(BillingExplanationRequest request);
}
