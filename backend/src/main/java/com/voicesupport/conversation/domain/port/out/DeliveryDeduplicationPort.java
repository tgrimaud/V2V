package com.voicesupport.conversation.domain.port.out;

// Outbound port for at-least-once channel delivery de-duplication (TASK-BE-037 / ADR-0009).
// `registerIfNew` atomically reserves an idempotency key and reports whether it was previously
// unseen: true = first delivery (now reserved), false = duplicate delivery. The reservation is
// what suppresses concurrent/repeat processing; it is confirmed by simply leaving it in place on a
// successful turn, or `release`d when the turn fails so a legitimate retry with the same key is
// reprocessed rather than swallowed. Implementations bound the retained key set; a shared/
// distributed store can replace the process-local one behind this port without touching the domain.
public interface DeliveryDeduplicationPort {

    boolean registerIfNew(String idempotencyKey);

    void release(String idempotencyKey);
}
