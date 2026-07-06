package com.voicesupport.infrastructure.adapter.out.persistence;

import com.voicesupport.domain.model.ConversationEvent;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

@Entity
@Table(name = "conversation_event")
public class ConversationEventEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "conversation_id", nullable = false)
    private String conversationId;

    @Column(name = "channel", nullable = false)
    private String channel;

    @Column(name = "question", nullable = false, columnDefinition = "TEXT")
    private String question;

    @Column(name = "answer", nullable = false, columnDefinition = "TEXT")
    private String answer;

    @Column(name = "citation_count", nullable = false)
    private int citationCount;

    @Column(name = "latency_ms", nullable = false)
    private long latencyMs;

    @Column(name = "escalated", nullable = false)
    private boolean escalated;

    @Column(name = "created_at", nullable = false)
    private Instant timestamp;

    protected ConversationEventEntity() {
    }

    public static ConversationEventEntity fromDomain(ConversationEvent event) {
        ConversationEventEntity entity = new ConversationEventEntity();
        entity.conversationId = event.conversationId();
        entity.channel = event.channel();
        entity.question = event.question();
        entity.answer = event.answer();
        entity.citationCount = event.citationCount();
        entity.latencyMs = event.latencyMs();
        entity.escalated = event.escalated();
        entity.timestamp = event.timestamp();
        return entity;
    }

    public ConversationEvent toDomain() {
        return new ConversationEvent(conversationId, channel, question, answer,
                citationCount, latencyMs, escalated, timestamp);
    }
}
