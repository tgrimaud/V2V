package com.voicesupport.infrastructure.adapter.out.persistence;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface ConversationEventRepository extends JpaRepository<ConversationEventEntity, Long> {

    long countByEscalatedTrue();

    List<ConversationEventEntity> findAllByOrderByIdAsc();

    @Query("select avg(event.latencyMs) from ConversationEventEntity event")
    Double averageLatencyMs();
}
