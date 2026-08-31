package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.ChannelEnvelope;
import com.voicesupport.conversation.domain.port.out.DeliveryDeduplicationPort;

// Decides whether a channel delivery is a duplicate that must not be reprocessed (TASK-BE-037).
// A delivery is de-duplicated only when the envelope carries an idempotency signal (explicit key
// or message id); channels without one (e.g. the current web path) are always first deliveries,
// so existing behaviour is unchanged. No channel-specific rule lives here (ADR-0009).
//
// `isDuplicate` atomically reserves the key: the first delivery reserves and proceeds, a concurrent
// or repeat delivery of the same key is a duplicate. The caller must confirm the reservation by
// completing the turn successfully (nothing to do), or call `releaseOnFailure` when the turn fails
// so a legitimate retry with the same key is reprocessed rather than dropped.
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

    public void releaseOnFailure(ChannelEnvelope envelope) {
        if (envelope == null || !envelope.hasIdempotencySignal()) {
            return;
        }
        deduplicationStore.release(envelope.effectiveIdempotencyKey());
    }
}
