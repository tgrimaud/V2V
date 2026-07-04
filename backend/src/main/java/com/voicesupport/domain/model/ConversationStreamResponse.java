package com.voicesupport.domain.model;

import java.util.List;

public record ConversationStreamResponse(
        TokenStream tokens,
        List<Citation> citations,
        boolean escalated,
        boolean guardrailBlocked,
        String agentId,
        String agentName
) {}
