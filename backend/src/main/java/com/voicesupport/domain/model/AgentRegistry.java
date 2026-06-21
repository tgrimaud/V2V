package com.voicesupport.domain.model;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

public class AgentRegistry {

    private final Map<String, AgentProfile> agents;
    private final AgentProfile defaultAgent;

    public AgentRegistry(List<AgentProfile> profiles, String defaultAgentId) {
        this.agents = profiles.stream()
                .collect(Collectors.toMap(AgentProfile::id, Function.identity()));
        this.defaultAgent = agents.get(defaultAgentId);
        if (defaultAgent == null) {
            throw new IllegalArgumentException("Default agent '%s' not found in registry".formatted(defaultAgentId));
        }
    }

    public Optional<AgentProfile> findById(String agentId) {
        return Optional.ofNullable(agents.get(agentId));
    }

    public AgentProfile getDefault() {
        return defaultAgent;
    }

    public List<AgentProfile> allProfiles() {
        return List.copyOf(agents.values());
    }
}
