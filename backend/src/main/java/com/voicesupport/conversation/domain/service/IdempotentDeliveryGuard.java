package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.ChannelEnvelope;
import com.voicesupport.conversation.domain.port.out.DeliveryDeduplicationPort;

// Decides whether a channel delivery is a duplicate that must not be reprocessed (TASK-BE-037).
// A delivery is de-duplicated only when the envelope carries an idempotency signal (explicit key
// or message id); channels without one (e.g. the current web path) are always first deliveries,
// so existing behaviour is unchanged. No channel-specific rule lives here (ADR-0009).
public class IdempotentDeliveryGuard {

    private final DeliveryDeduplicationPort deduplicationStore;

    public IdempotentDeliveryGuard(DeliveryDeduplicationPort deduplicationStore) {
        this.deduplicationStore = deduplicationStore;
    }

    public boolean isDuplicate(ChannelEnvelope envelope) {
        if (envelope == null || !envelope.hasIdempotencySignal()) {
            return false;
        }
        return !deduplicationStore.registerIfNew(envelope.effectiveIdempotencyKey());
    }
}
