package com.voicesupport.conversation.infrastructure.adapter.out.idempotency;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("InMemoryDeliveryDeduplicationAdapter registerIfNew + release")
class InMemoryDeliveryDeduplicationAdapterTest {

    @Test
    void records_a_new_key_once_and_reports_repeats_as_seen() {
        // GIVEN an empty bounded store
        var store = new InMemoryDeliveryDeduplicationAdapter(1000);

        // WHEN the same key is registered twice
        boolean first = store.registerIfNew("idem-1");
        boolean second = store.registerIfNew("idem-1");

        // THEN only the first registration is new
        assertThat(first).isTrue();
        assertThat(second).isFalse();
    }

    @Test
    void treats_a_blank_key_as_new_so_it_never_blocks_processing() {
        // GIVEN a store
        var store = new InMemoryDeliveryDeduplicationAdapter(1000);

        // WHEN a null/blank key is registered
        // THEN it is reported as new (no dedup without a real key)
        assertThat(store.registerIfNew(null)).isTrue();
        assertThat(store.registerIfNew("   ")).isTrue();
    }

    @Test
    void evicts_the_eldest_key_past_the_capacity() {
        // GIVEN a store bounded to a single key that has recorded k1
        var store = new InMemoryDeliveryDeduplicationAdapter(1);
        store.registerIfNew("k1");

        // WHEN a second distinct key is recorded, evicting k1
        store.registerIfNew("k2");

        // THEN k1 is forgotten (re-registers as new) — bounded-store trade-off
        assertThat(store.registerIfNew("k1")).isTrue();
    }

    @Test
    void release_then_reregister_is_new() {
        // GIVEN a store where a key is registered and its repeat is seen as a duplicate
        var store = new InMemoryDeliveryDeduplicationAdapter(1000);
        assertThat(store.registerIfNew("idem-1")).isTrue();
        assertThat(store.registerIfNew("idem-1")).isFalse();

        // WHEN the reserved key is released (e.g. its turn failed)
        store.release("idem-1");

        // THEN the freed key registers as new again so a legitimate retry is reprocessed
        assertThat(store.registerIfNew("idem-1")).isTrue();
    }

    @Test
    void releasing_an_absent_or_blank_key_is_a_safe_no_op_and_does_not_evict_a_different_key() {
        // GIVEN a store holding one reserved key
        var store = new InMemoryDeliveryDeduplicationAdapter(1000);
        store.registerIfNew("idem-kept");

        // WHEN never-registered, null and blank keys are released
        store.release("idem-never");
        store.release(null);
        store.release("   ");

        // THEN the retained key is untouched — still a duplicate, no accidental eviction
        assertThat(store.registerIfNew("idem-kept")).isFalse();
    }
}
