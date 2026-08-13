package com.voicesupport.knowledge.domain.service;

import java.util.regex.Pattern;

// TASK-BE-029 (BUG-003 / OQ-008): strips a leading conversational greeting from the retrieval
// query BEFORE it is embedded, so phrasing variants like "Bonjour, internet est lent" and
// "internet est lent" retrieve the same evidence. Pure domain, deterministic, no store change.
//
// Scope guarantees:
//  - Only the embedding query is rewritten. The raw question still drives the input guardrail,
//    the LLM prompt and the logs (those run upstream on the original text) — this class is only
//    called by KnowledgeRetrievalService just before VectorSearchPort.search().
//  - The remainder of the query is preserved verbatim (case + accents kept — accents matter for
//    French embeddings); only the leading greeting run is removed.
//  - A whole-utterance greeting is never emptied into a blank query: if stripping leaves nothing,
//    the original query is returned (whole-utterance greetings are already blocked by the input
//    guardrail before retrieval; this is a defensive fallback).
//
// The greeting vocabulary is intentionally aligned with InputGuardrail.GREETING_PATTERNS
// (conversation domain). It is duplicated here rather than imported to respect the context
// boundary (ADR-0027) — the two lists must be kept consistent by convention.
public final class QueryNormalizer {

    // Leading run of one or more greeting tokens, each followed by at least one separator
    // (whitespace and/or punctuation). Word boundary (\b) after the token prevents matching a
    // greeting inside a longer word ("salut" in "salutations", "hi" in "history"). The remainder
    // after the run is the normalized query.
    private static final Pattern LEADING_GREETING = Pattern.compile(
            "^(?:\\s*(?:bonjour|bonsoir|salut|coucou|hey|hello|hi|yo|bjr|slt|cc|bsr|hola|hallo"
                    + "|good\\s+(?:morning|afternoon|evening|day))\\b[\\s,;:.!?…\\-]+)+",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

    // Returns the query with any leading greeting run removed, or the original query unchanged when
    // there is no leading greeting (or stripping would empty the query). Never returns null unless
    // the input is null.
    public String normalize(String query) {
        if (query == null || query.isBlank()) {
            return query;
        }
        String stripped = LEADING_GREETING.matcher(query).replaceFirst("").strip();
        return stripped.isEmpty() ? query : stripped;
    }

    // True when normalize(query) would change the query (a leading greeting is present and
    // stripping leaves real content). Lets callers observe only the turns that were rewritten.
    public boolean rewrites(String query) {
        if (query == null || query.isBlank()) {
            return false;
        }
        String stripped = LEADING_GREETING.matcher(query).replaceFirst("").strip();
        return !stripped.isEmpty() && !stripped.equals(query.strip());
    }
}
