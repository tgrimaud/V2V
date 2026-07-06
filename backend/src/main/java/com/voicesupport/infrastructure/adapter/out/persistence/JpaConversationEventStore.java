package com.voicesupport.infrastructure.adapter.out.persistence;

import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.port.out.ConversationEventStore;

import java.util.List;

public class JpaConversationEventStore implements ConversationEventStore {

    private final ConversationEventRepository repository;

    public JpaConversationEventStore(ConversationEventRepository repository) {
        this.repository = repository;
    }

    @Override
    public void save(ConversationEvent event) {
        repository.save(ConversationEventEntity.fromDomain(event));
    }

    @Override
    public List<ConversationEvent> findAll() {
        return repository.findAllByOrderByIdAsc().stream()
                .map(ConversationEventEntity::toDomain)
                .toList();
    }

    @Override
    public long countTotal() {
        return repository.count();
    }

    @Override
    public long countEscalated() {
        return repository.countByEscalatedTrue();
    }

    @Override
    public double averageLatencyMs() {
        Double average = repository.averageLatencyMs();
        return average != null ? average : 0.0;
    }
}
