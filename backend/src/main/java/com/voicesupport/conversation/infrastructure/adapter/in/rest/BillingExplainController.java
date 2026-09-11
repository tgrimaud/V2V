package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffCommand;
import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoffReference;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.AnswerBillingQuestionUseCase;
import com.voicesupport.conversation.domain.port.in.PrepareEscalationHandoffUseCase;
import com.voicesupport.shared.observability.CorrelationId;
import com.voicesupport.shared.web.rest.ErrorResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Locale;

// Dedicated billing-explanation endpoint (TASK-BE-045, ADR-0051 D3c): the deterministic billing chain
// behind the answer engine, exposed as its own surface so /converse and the voice runtime stay
// untouched until a follow-up wires billing routing into /converse. api-key gated via
// WebSecurityMvcConfig (same as /answer). On an escalation turn the response carries only the
// by-reference hand-off token (ADR-0019 / DEC-013); ordinary turns omit it.
@RestController
@RequestMapping("/api/conversation")
@Tag(name = "Conversation")
public class BillingExplainController {

    private static final Logger log = LoggerFactory.getLogger(BillingExplainController.class);
    private static final String LISTEN_PROMPT = "Je vous écoute, posez-moi votre question sur votre facture.";

    private final AnswerBillingQuestionUseCase answerBillingQuestionUseCase;
    private final PrepareEscalationHandoffUseCase prepareEscalationHandoffUseCase;

    public BillingExplainController(
            AnswerBillingQuestionUseCase answerBillingQuestionUseCase,
            PrepareEscalationHandoffUseCase prepareEscalationHandoffUseCase) {
        this.answerBillingQuestionUseCase = answerBillingQuestionUseCase;
        this.prepareEscalationHandoffUseCase = prepareEscalationHandoffUseCase;
    }

    @PostMapping("/billing-explain")
    @Operation(summary = "Explain a bill (deterministic billing chain)",
            description = "Resolves identity (BR-002-1), compares the two most recent invoices, gates "
                    + "confidence (BR-003) and returns a grounded explanation the LLM only rephrases "
                    + "(DEC-002), or a safe hand-off. Never invents amounts; escalates fail-closed.")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "A safe, contract-shaped billing answer."),
            @ApiResponse(responseCode = "401", description = "Missing/invalid x-api-key when a shared secret is set.",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "503", description = "A required upstream is unavailable.",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    public ResponseEntity<BillingExplainResponse> explain(
            @RequestBody BillingExplainRequest request, HttpServletResponse httpResponse) {
        establishContext(request, httpResponse);
        if (!request.hasTranscript()) {
            return ResponseEntity.ok(new BillingExplainResponse(LISTEN_PROMPT, null, null));
        }
        long start = System.nanoTime();
        GeneratedAnswer answer = answerBillingQuestionUseCase.answer(request.toDomainRequest());
        EscalationHandoffReference reference = prepareHandoffIfEscalated(request, answer);
        logTurn(request, answer, reference, elapsedMs(start));
        return ResponseEntity.ok(BillingExplainResponse.from(answer, reference));
    }

    private void establishContext(BillingExplainRequest request, HttpServletResponse httpResponse) {
        CorrelationId.set(request.correlationId());
        CorrelationId.setChannel(request.channel());
        httpResponse.setHeader(CorrelationId.HEADER, CorrelationId.current());
    }

    private EscalationHandoffReference prepareHandoffIfEscalated(
            BillingExplainRequest request, GeneratedAnswer answer) {
        if (!answer.requiresEscalation()) {
            return null;
        }
        return prepareEscalationHandoffUseCase.prepare(new EscalationHandoffCommand(
                request.channel(), null, null, request.conversationId(), answer.escalation(),
                answer.text(), request.transcript(), List.of()));
    }

    // Privacy-safe: never logs the transcript or the customer reference — only the outcome shape.
    private void logTurn(
            BillingExplainRequest request, GeneratedAnswer answer, EscalationHandoffReference reference, long ms) {
        log.info("[BILLING-EXPLAIN] channel={} correlation_id={} grounded={} escalated={} reason={} "
                        + "confidence={} chars={} duration_ms={}",
                nullSafe(request.channel()), CorrelationId.current(), answer.grounded(),
                answer.requiresEscalation(), reference != null ? reference.reasonCode() : "n/a",
                formatConfidence(answer.confidence()), answer.text() != null ? answer.text().length() : 0, ms);
    }

    private String nullSafe(String value) {
        String clean = CorrelationId.sanitize(value);
        return clean == null || clean.isBlank() ? "n/a" : clean;
    }

    private String formatConfidence(Double confidence) {
        return confidence == null ? "n/a" : String.format(Locale.ROOT, "%.4f", confidence);
    }

    private static long elapsedMs(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }
}
