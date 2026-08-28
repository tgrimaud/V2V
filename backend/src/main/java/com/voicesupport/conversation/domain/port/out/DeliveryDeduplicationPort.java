package com.voicesupport.conversation.domain.port.out;

// Outbound port for at-least-once channel delivery de-duplication (TASK-BE-037 / ADR-0009).
// `registerIfNew` atomically records an idempotency key and reports whether it was previously
// unseen: true = first delivery (now recorded), false = duplicate delivery. Implementations bound
// the retained key set; a shared/distributed store can replace the process-local one behind this
// port without touching the domain.
public interface DeliveryDeduplicationPort {

    boolean registerIfNew(String idempotencyKey);
}
