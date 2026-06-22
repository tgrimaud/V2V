package com.voicesupport.infrastructure.adapter.in.rest;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.port.in.AskQuestionUseCase;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/conversation")
public class ConversationController {

    private final AskQuestionUseCase askQuestionUseCase;

    public ConversationController(AskQuestionUseCase askQuestionUseCase) {
        this.askQuestionUseCase = askQuestionUseCase;
    }

    @PostMapping("/ask")
    public ResponseEntity<AskResponse> ask(@RequestBody AskRequest request) {
        String conversationId = request.conversationId() != null ?
                request.conversationId() : "default";

        ConversationResponse response = askQuestionUseCase.ask(conversationId, request.question());

        List<CitationDto> citations = response.citations().stream()
                .map(c -> new CitationDto(c.source(), c.section(), c.relevantText(), c.score()))
                .toList();

        return ResponseEntity.ok(new AskResponse(response.answer(), citations, conversationId,
                response.agentId(), response.agentName(), response.guardrailBlocked()));
    }

    public record AskRequest(String question,
                             @JsonProperty("conversation_id") String conversationId) {}

    public record AskResponse(String answer, List<CitationDto> citations, String conversationId,
                              @JsonProperty("agent_id") String agentId,
                              @JsonProperty("agent_name") String agentName,
                              @JsonProperty("guardrail_blocked") boolean guardrailBlocked) {}

    public record CitationDto(String source, String section, String relevantText, double score) {}
}
