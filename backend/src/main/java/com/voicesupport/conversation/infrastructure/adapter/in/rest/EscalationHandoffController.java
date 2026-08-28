package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import com.voicesupport.conversation.domain.port.in.FetchEscalationHandoffUseCase;
import com.voicesupport.shared.observability.CorrelationId;
import com.voicesupport.shared.web.rest.ErrorResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Optional;

// By-reference hand-off fetch (TASK-BE-036 / DEC-013 / ADR-0040). The escalation path emits an
// opaque handoff_id on the channel; the advisor desktop (or a widget) retrieves the full audited
// EscalationHandoff here on demand, so the payload + PII stay backend-owned and auditable. The
// api-key gate is applied by WebSecurityMvcConfig (same secret as the other conversation endpoints);
// an unknown id returns the sanitized ErrorResponse (404) without echoing any internal detail.
@RestController
@RequestMapping("/api/conversation")
@Tag(name = "Conversation")
public class EscalationHandoffController {

    private static final String ERR_NOT_FOUND = "ERR_HANDOFF_NOT_FOUND";
    private static final String MSG_NOT_FOUND = "No escalation hand-off matches the requested reference.";

    private final FetchEscalationHandoffUseCase fetchEscalationHandoffUseCase;

    public EscalationHandoffController(FetchEscalationHandoffUseCase fetchEscalationHandoffUseCase) {
        this.fetchEscalationHandoffUseCase = fetchEscalationHandoffUseCase;
    }

    @GetMapping("/escalation-handoffs/{handoff_id}")
    @Operation(summary = "Fetch an escalation hand-off by reference",
            description = "Returns the full audited EscalationHandoff (ADR-0019) for a handoff_id minted on "
                    + "escalation. The payload + PII stay backend-owned (DEC-013); only the reference travels "
                    + "on the channel. Unknown id returns the sanitized ErrorResponse (404).")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "The audited hand-off payload."),
            @ApiResponse(responseCode = "401", description = "Missing/invalid x-api-key when a shared secret is set.",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "404", description = "No hand-off matches the reference.",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    public ResponseEntity<Object> fetch(
            @Parameter(description = "Opaque hand-off reference minted on escalation.")
            @PathVariable("handoff_id") String handoffId) {
        Optional<EscalationHandoff> found = fetchEscalationHandoffUseCase.fetch(HandoffId.of(handoffId));
        return found
                .<ResponseEntity<Object>>map(handoff ->
                        ResponseEntity.ok(EscalationHandoffResponse.from(HandoffId.of(handoffId), handoff)))
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND)
                        .body(ErrorResponse.of(ERR_NOT_FOUND, MSG_NOT_FOUND, CorrelationId.current())));
    }
}
