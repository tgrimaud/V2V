package com.voicesupport.conversation.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("ChannelEnvelope")
class ChannelEnvelopeTest {

    @Test
    void normalizes_channel_and_strips_control_characters_from_fields() {
        // GIVEN a channel-tagged delivery with padded/upper channel and CR/LF-laced ids
        // WHEN the envelope is built
        ChannelEnvelope envelope = ChannelEnvelope.of(
                "  GENESYS ", "sess\r\n-9", "evt-1", "idem-1", "voice", "handoff-7");

        // THEN the channel is lowercased/trimmed and control chars are stripped
        assertThat(envelope.channel()).isEqualTo("genesys");
        assertThat(envelope.externalSessionId()).isEqualTo("sess-9");
        assertThat(envelope.replyMode()).isEqualTo(ReplyMode.VOICE);
        assertThat(envelope.escalationContext()).isEqualTo("handoff-7");
    }

    @Test
    void collapses_blank_optionals_to_null_and_defaults_reply_mode() {
        // GIVEN a delivery with blank optional fields and no reply mode
        // WHEN the envelope is built
        ChannelEnvelope envelope = ChannelEnvelope.of("web", "  ", "  ", "  ", "  ", "  ");

        // THEN blank optionals become null and the reply mode defaults to voice
        assertThat(envelope.externalSessionId()).isNull();
        assertThat(envelope.messageId()).isNull();
        assertThat(envelope.idempotencyKey()).isNull();
        assertThat(envelope.escalationContext()).isNull();
        assertThat(envelope.replyMode()).isEqualTo(ReplyMode.VOICE);
    }

    @Test
    void conversation_key_is_the_external_session_id() {
        // GIVEN a Genesys delivery keyed on its conversation id
        // WHEN the conversation key is read
        // THEN it is the external session id so the whole call stays one conversation
        ChannelEnvelope envelope = ChannelEnvelope.of("genesys", "genesys-conv-9", null, null, "voice", null);

        assertThat(envelope.conversationKey()).isEqualTo("genesys-conv-9");
        assertThat(envelope.hasExternalSession()).isTrue();
    }

    @Test
    void has_no_idempotency_signal_when_neither_key_nor_message_id_present() {
        // GIVEN a web-style delivery with no idempotency data (the current path)
        // WHEN the signal is checked
        // THEN there is none, so it is never treated as a duplicate
        ChannelEnvelope envelope = ChannelEnvelope.of("web", "c1", null, null, "voice", null);

        assertThat(envelope.hasIdempotencySignal()).isFalse();
        assertThat(envelope.effectiveIdempotencyKey()).isNull();
    }

    @Test
    void prefers_the_explicit_idempotency_key_when_present() {
        // GIVEN a delivery carrying an explicit idempotency key
        // WHEN the effective key is derived
        // THEN the explicit key is used verbatim
        ChannelEnvelope envelope = ChannelEnvelope.of("genesys", "s9", "evt-1", "idem-42", "voice", null);

        assertThat(envelope.hasIdempotencySignal()).isTrue();
        assertThat(envelope.effectiveIdempotencyKey()).isEqualTo("idem-42");
    }

    @Test
    void derives_the_idempotency_key_from_channel_session_and_message_id() {
        // GIVEN a delivery with only a message id (no explicit key)
        // WHEN the effective key is derived
        // THEN it is a stable composite of channel + session + message id
        ChannelEnvelope envelope = ChannelEnvelope.of("genesys", "s9", "evt-1", null, "voice", null);

        assertThat(envelope.effectiveIdempotencyKey()).isEqualTo("genesys:s9:evt-1");
    }

    @Test
    void rejects_an_unknown_reply_mode() {
        // GIVEN a delivery with an unsupported reply mode
        // WHEN / THEN building the envelope is rejected (mapped to 400 upstream)
        assertThatThrownBy(() -> ChannelEnvelope.of("genesys", "s9", null, null, "smoke-signal", null))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
