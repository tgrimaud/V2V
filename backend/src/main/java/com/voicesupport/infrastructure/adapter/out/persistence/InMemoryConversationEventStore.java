package com.voicesupport.infrastructure.adapter.out.persistence;

import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.port.out.ConversationEventStore;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class InMemoryConversationEventStore implements ConversationEventStore {

    private final List<ConversationEvent> events = new CopyOnWriteArrayList<>();

    @Override
    public void save(ConversationEvent event) {
        events.add(event);
    }

    @Override
    public List<ConversationEvent> findAll() {
        return List.copyOf(events);
    }

    @Override
    public long countTotal() {
        return events.size();
    }

    @Override
    public long countEscalated() {
        return events.stream().filter(ConversationEvent::escalated).count();
    }

    @Override
    public double averageLatencyMs() {
        if (events.isEmpty()) return 0.0;
        return events.stream().mapToLong(ConversationEvent::latencyMs).average().orElse(0.0);
    }
}
