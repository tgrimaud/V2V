package com.voicesupport.billing.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("PdfSource (immutability + validation)")
class PdfSourceTest {

    @Test
    void copies_the_content_defensively_in_and_out() {
        // GIVEN a mutable byte array
        byte[] original = {1, 2, 3};
        PdfSource source = new PdfSource("ref", original);

        // WHEN the caller mutates the original and the returned copy
        original[0] = 9;
        source.content()[1] = 9;

        // THEN the source's content is unaffected
        assertThat(source.content()).containsExactly(1, 2, 3);
        assertThat(source.isEmpty()).isFalse();
    }

    @Test
    void rejects_a_blank_reference() {
        // GIVEN / WHEN / THEN a blank reference is rejected
        assertThatThrownBy(() -> new PdfSource("  ", new byte[]{1}))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
