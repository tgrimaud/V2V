package com.voicesupport.domain.port.out;

import com.voicesupport.domain.model.ConversationEvent;

import java.util.List;

public interface ConversationEventStore {

    void save(ConversationEvent event);

    List<ConversationEvent> findAll();

    long countTotal();

    long countEscalated();

    double averageLatencyMs();
}
