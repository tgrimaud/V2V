package com.voicesupport.conversation.infrastructure.adapter.out.handoff;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.EscalationReason;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("InMemoryEscalationHandoffAdapter store + findById round-trip")
class InMemoryEscalationHandoffAdapterTest {

    @Test
    void stores_a_handoff_and_serves_it_back_by_the_minted_id() {
        // GIVEN a store and an audited hand-off
        var store = new InMemoryEscalationHandoffAdapter(1000);
        EscalationHandoff handoff = handoff("Pourquoi ma facture a augmenté ?");

        // WHEN it is stored and fetched by the minted id
        HandoffId id = store.store(handoff);
        var found = store.findById(id);

        // THEN the full payload (including PII) is returned by reference
        assertThat(id.value()).isNotBlank();
        assertThat(found).contains(handoff);
        assertThat(found.orElseThrow().lastUserMessage()).isEqualTo("Pourquoi ma facture a augmenté ?");
    }

    @Test
    void an_unknown_id_returns_empty() {
        // GIVEN a store that never saw the id
        var store = new InMemoryEscalationHandoffAdapter(1000);

        // WHEN an unknown id is fetched
        // THEN nothing is returned (the controller maps this to a sanitized 404)
        assertThat(store.findById(HandoffId.of("does-not-exist"))).isEmpty();
    }

    @Test
    void mints_a_distinct_id_per_store() {
        // GIVEN a store
        var store = new InMemoryEscalationHandoffAdapter(1000);

        // WHEN the same payload is stored twice
        HandoffId first = store.store(handoff("q1"));
        HandoffId second = store.store(handoff("q2"));

        // THEN each store mints a distinct opaque reference
        assertThat(first.value()).isNotEqualTo(second.value());
    }

    @Test
    void evicts_the_eldest_handoff_past_the_capacity() {
        // GIVEN a store bounded to a single hand-off that has recorded one
        var store = new InMemoryEscalationHandoffAdapter(1);
        HandoffId first = store.store(handoff("q1"));

        // WHEN a second distinct hand-off is stored, evicting the first
        store.store(handoff("q2"));

        // THEN the eldest reference is forgotten — bounded-store trade-off
        assertThat(store.findById(first)).isEmpty();
    }

    private static EscalationHandoff handoff(String lastUserMessage) {
        return EscalationHandoff.builder()
                .channel("genesys")
                .externalSessionId("genesys-conv-9")
                .conversationId("genesys-conv-9")
                .reason(EscalationReason.LOW_CONFIDENCE)
                .summary("Mise en relation avec un conseiller.")
                .lastUserMessage(lastUserMessage)
                .createdAt(Instant.parse("2026-08-28T10:15:30Z"))
                .build();
    }
}
