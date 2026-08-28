package com.voicesupport.conversation.infrastructure.adapter.out.idempotency;

import com.voicesupport.conversation.domain.port.out.DeliveryDeduplicationPort;

import java.util.LinkedHashMap;
import java.util.Map;

// Process-local, bounded de-duplication store (TASK-BE-037). Keeps at most `maxKeys` recently seen
// idempotency keys in access-ordered LRU order; the eldest key is evicted past the cap. Suitable
// for a single-node pilot — a shared/distributed store (Redis, DB) is a later concern, swappable
// behind DeliveryDeduplicationPort. All access is synchronized on the backing map so concurrent
// deliveries stay consistent.
public class InMemoryDeliveryDeduplicationAdapter implements DeliveryDeduplicationPort {

    private static final Object PRESENT = new Object();

    private final Map<String, Object> seen;

    public InMemoryDeliveryDeduplicationAdapter(int maxKeys) {
        int cap = Math.max(1, maxKeys);
        this.seen = new LinkedHashMap<>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, Object> eldest) {
                return size() > cap;
            }
        };
    }

    @Override
    public boolean registerIfNew(String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            return true;
        }
        synchronized (seen) {
            return seen.put(idempotencyKey, PRESENT) == null;
        }
    }

    // Drops a previously-reserved key so a turn that failed and is legitimately retried with the
    // same idempotency key is reprocessed instead of being swallowed as a duplicate (TASK-BE-037).
    @Override
    public void release(String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            return;
        }
        synchronized (seen) {
            seen.remove(idempotencyKey);
        }
    }
}
