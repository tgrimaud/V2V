package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.ChannelEnvelope;
import com.voicesupport.conversation.domain.port.out.DeliveryDeduplicationPort;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("IdempotentDeliveryGuard.isDuplicate")
class IdempotentDeliveryGuardTest {

    // Manual fake (no Mockito): mirrors an at-least-once store reserving/releasing seen keys.
    private static final class FakeDeduplicationStore implements DeliveryDeduplicationPort {
        private final Set<String> seen = new HashSet<>();

        @Override
        public boolean registerIfNew(String idempotencyKey) {
            return seen.add(idempotencyKey);
        }

        @Override
        public void release(String idempotencyKey) {
            seen.remove(idempotencyKey);
        }
    }

    private ChannelEnvelope withKey(String idempotencyKey) {
        return ChannelEnvelope.of("genesys", "s9", "evt-1", idempotencyKey, "voice", null);
    }

    @Test
    void a_delivery_without_an_idempotency_signal_is_never_a_duplicate() {
        // GIVEN a web delivery carrying no idempotency data
        var guard = new IdempotentDeliveryGuard(new FakeDeduplicationStore());
        ChannelEnvelope envelope = ChannelEnvelope.of("web", "c1", null, null, "voice", null);

        // WHEN checked twice
        // THEN it is always a first delivery (existing web path unaffected)
        assertThat(guard.isDuplicate(envelope)).isFalse();
        assertThat(guard.isDuplicate(envelope)).isFalse();
    }

    @Test
    void the_first_delivery_is_processed_and_a_repeat_is_a_duplicate() {
        // GIVEN a guard over an empty store and a delivery with an idempotency key
        var guard = new IdempotentDeliveryGuard(new FakeDeduplicationStore());
        ChannelEnvelope envelope = withKey("idem-42");

        // WHEN the same key is delivered twice
        boolean first = guard.isDuplicate(envelope);
        boolean second = guard.isDuplicate(envelope);

        // THEN only the second delivery is flagged as a duplicate
        assertThat(first).isFalse();
        assertThat(second).isTrue();
    }

    @Test
    void a_different_idempotency_key_is_a_new_delivery() {
        // GIVEN a guard that has already seen one key
        var guard = new IdempotentDeliveryGuard(new FakeDeduplicationStore());
        guard.isDuplicate(withKey("idem-1"));

        // WHEN a delivery with a different key arrives
        boolean duplicate = guard.isDuplicate(withKey("idem-2"));

        // THEN it is treated as a new delivery
        assertThat(duplicate).isFalse();
    }

    @Test
    void a_retry_after_a_failed_turn_is_reprocessed_when_the_reservation_is_released() {
        // GIVEN a first delivery that reserved its key but whose turn failed
        var guard = new IdempotentDeliveryGuard(new FakeDeduplicationStore());
        ChannelEnvelope envelope = withKey("idem-42");
        assertThat(guard.isDuplicate(envelope)).isFalse();
        guard.releaseOnFailure(envelope);

        // WHEN the same key is legitimately retried
        boolean retry = guard.isDuplicate(envelope);

        // THEN the retry is reprocessed, not swallowed as a duplicate
        assertThat(retry).isFalse();
    }

    @Test
    void a_successfully_answered_turn_is_still_deduped_when_redelivered() {
        // GIVEN a first delivery that reserved its key and succeeded (no release)
        var guard = new IdempotentDeliveryGuard(new FakeDeduplicationStore());
        ChannelEnvelope envelope = withKey("idem-42");
        assertThat(guard.isDuplicate(envelope)).isFalse();

        // WHEN the same delivery arrives again
        boolean redelivery = guard.isDuplicate(envelope);

        // THEN the confirmed reservation still suppresses the duplicate
        assertThat(redelivery).isTrue();
    }

    @Test
    void releasing_a_delivery_without_an_idempotency_signal_is_a_no_op() {
        // GIVEN a web delivery carrying no idempotency data
        var guard = new IdempotentDeliveryGuard(new FakeDeduplicationStore());
        ChannelEnvelope envelope = ChannelEnvelope.of("web", "c1", null, null, "voice", null);

        // WHEN / THEN releasing it does not throw and it stays a first delivery
        guard.releaseOnFailure(envelope);
        assertThat(guard.isDuplicate(envelope)).isFalse();
    }
}
