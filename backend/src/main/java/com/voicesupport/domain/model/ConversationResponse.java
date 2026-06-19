package com.voicesupport.domain.model;

import java.util.List;

public record ConversationResponse(
        String answer,
        List<Citation> citations
) {}
