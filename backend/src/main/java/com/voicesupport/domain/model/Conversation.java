package com.voicesupport.domain.model;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class Conversation {

    private final String id;
    private final List<Turn> turns;
    private final Instant startedAt;
    private String sessionLanguage;
    private String currentAgentId;

    public Conversation() {
        this.id = UUID.randomUUID().toString();
        this.turns = new ArrayList<>();
        this.startedAt = Instant.now();
        this.sessionLanguage = "fr";
        this.currentAgentId = null;
    }

    public void addUserTurn(String text) {
        turns.add(new Turn(Role.USER, text, Instant.now()));
    }

    public void addAssistantTurn(String text, List<Citation> citations) {
        turns.add(new Turn(Role.ASSISTANT, text, Instant.now(), citations));
    }

    public List<Turn> lastTurns(int count) {
        int start = Math.max(0, turns.size() - count);
        return List.copyOf(turns.subList(start, turns.size()));
    }

    public String getId() { return id; }
    public List<Turn> getTurns() { return List.copyOf(turns); }
    public Instant getStartedAt() { return startedAt; }
    public String getSessionLanguage() { return sessionLanguage; }
    public void setSessionLanguage(String language) { this.sessionLanguage = language; }
    public String getCurrentAgentId() { return currentAgentId; }
    public void setCurrentAgentId(String agentId) { this.currentAgentId = agentId; }

    public enum Role { USER, ASSISTANT }

    public record Turn(Role role, String text, Instant timestamp, List<Citation> citations) {
        public Turn(Role role, String text, Instant timestamp) {
            this(role, text, timestamp, List.of());
        }
    }
}
