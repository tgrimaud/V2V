package com.voicesupport.conversation.domain.model.valueobject;

import java.util.Locale;

// Normalized channel envelope (TASK-BE-037 / ADR-0009): the channel-identity + idempotency data
// every channel adapter (web, WebRTC, telephony, WhatsApp, Genesys) carries so escalation,
// routing and conversation memory stay consistent across channels without per-channel forks. It
// is a pure value object — no channel-specific business rule lives here (ADR-0009); the Genesys
// (or any) adapter maps its native identifiers onto these fields. All fields are client-controlled
// and reach logs and the memory key, so `of(...)` strips control characters, trims, length-bounds
// and lowercases the channel; blank optionals collapse to null.
public record ChannelEnvelope(
        String channel,
        String externalSessionId,
        String messageId,
        String idempotencyKey,
        ReplyMode replyMode,
        String escalationContext) {

    private static final int MAX_LENGTH = 200;

    public ChannelEnvelope {
        replyMode = replyMode == null ? ReplyMode.VOICE : replyMode;
    }

    // Normalizing factory used at the channel boundary: sanitizes every client-controlled field,
    // lowercases the channel, resolves the reply mode (null/blank -> VOICE; unknown -> rejected)
    // and collapses blank optionals to null. Never rejects a blank channel/session so existing
    // channels that omit them keep their current stateless behaviour.
    public static ChannelEnvelope of(
            String channel, String externalSessionId, String messageId,
            String idempotencyKey, String replyMode, String escalationContext) {
        return new ChannelEnvelope(
                lower(sanitize(channel)),
                sanitize(externalSessionId),
                sanitize(messageId),
                sanitize(idempotencyKey),
                ReplyMode.fromCode(replyMode),
                sanitize(escalationContext));
    }

    // The coherent conversation/memory key for the channel (TASK-BE-037): a Genesys call keys on
    // its external_session_id so the whole call stays one conversation. Null/blank -> stateless.
    public String conversationKey() {
        return externalSessionId;
    }

    public boolean hasExternalSession() {
        return notBlank(externalSessionId);
    }

    // A delivery can be de-duplicated only when the channel supplied an explicit idempotency key or
    // a message id; channels supplying neither (e.g. the current web path) are never treated as
    // duplicates, preserving existing behaviour.
    public boolean hasIdempotencySignal() {
        return notBlank(idempotencyKey) || notBlank(messageId);
    }

    // Stable de-duplication key: the explicit idempotency key when present, otherwise derived from
    // channel + external_session_id + message_id so a duplicate delivery of the same inbound event
    // resolves to the same key. Null when there is no idempotency signal.
    public String effectiveIdempotencyKey() {
        if (notBlank(idempotencyKey)) {
            return idempotencyKey;
        }
        if (notBlank(messageId)) {
            return String.join(":", nullToEmpty(channel), nullToEmpty(externalSessionId), messageId);
        }
        return null;
    }

    private static String sanitize(String value) {
        if (value == null) {
            return null;
        }
        String stripped = value.strip();
        StringBuilder builder = new StringBuilder(Math.min(stripped.length(), MAX_LENGTH));
        for (int i = 0; i < stripped.length() && builder.length() < MAX_LENGTH; i++) {
            char c = stripped.charAt(i);
            if (!Character.isISOControl(c)) {
                builder.append(c);
            }
        }
        String cleaned = builder.toString();
        return cleaned.isBlank() ? null : cleaned;
    }

    private static String lower(String value) {
        return value == null ? null : value.toLowerCase(Locale.ROOT);
    }

    private static boolean notBlank(String value) {
        return value != null && !value.isBlank();
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
