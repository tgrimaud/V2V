package com.voicesupport.infrastructure.adapter.out.persistence;

import com.voicesupport.domain.model.ConversationEvent;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ConversationEventEntityTest {

    @Test
    void from_domain_round_trips_event_fields() {
        // GIVEN
        ConversationEvent event = new ConversationEvent("conv-1", "voice", "question",
                "answer", 2, 123, false, Instant.parse("2026-07-06T08:00:00Z"));

        // WHEN
        ConversationEvent roundTrip = ConversationEventEntity.fromDomain(event).toDomain();

        // THEN
        assertEquals("conv-1", roundTrip.conversationId());
        assertEquals("voice", roundTrip.channel());
        assertEquals("question", roundTrip.question());
        assertEquals("answer", roundTrip.answer());
        assertEquals(2, roundTrip.citationCount());
        assertEquals(123, roundTrip.latencyMs());
        assertFalse(roundTrip.escalated());
        assertEquals(event.timestamp(), roundTrip.timestamp());
    }
}
