package com.voicesupport.conversation.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("ReplyMode.fromCode")
class ReplyModeTest {

    @Test
    void maps_known_codes_case_insensitively() {
        // GIVEN wire codes for the supported modes
        // WHEN mapped
        // THEN each resolves to its mode
        assertThat(ReplyMode.fromCode("voice")).isEqualTo(ReplyMode.VOICE);
        assertThat(ReplyMode.fromCode("  TEXT ")).isEqualTo(ReplyMode.TEXT);
    }

    @Test
    void defaults_to_voice_when_null_or_blank() {
        // GIVEN no reply mode supplied
        // WHEN mapped
        // THEN it defaults to the voice-first mode
        assertThat(ReplyMode.fromCode(null)).isEqualTo(ReplyMode.VOICE);
        assertThat(ReplyMode.fromCode("  ")).isEqualTo(ReplyMode.VOICE);
    }

    @Test
    void rejects_an_unknown_reply_mode_without_echoing_the_input() {
        // GIVEN an unsupported reply mode code
        // WHEN / THEN it is rejected and the raw input is not echoed (no log injection)
        assertThatThrownBy(() -> ReplyMode.fromCode("carrier-pigeon"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("unsupported reply_mode");
    }
}
