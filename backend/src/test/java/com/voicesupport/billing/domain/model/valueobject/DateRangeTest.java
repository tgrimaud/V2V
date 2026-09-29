package com.voicesupport.billing.domain.model.valueobject;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("DateRange (closed billing interval)")
class DateRangeTest {

    @Test
    void accepts_a_range_whose_end_is_on_or_after_the_start() {
        // GIVEN a valid start/end
        LocalDate start = LocalDate.of(2026, 9, 12);
        LocalDate end = LocalDate.of(2026, 10, 11);

        // WHEN the range is built
        DateRange range = DateRange.of(start, end);

        // THEN it carries both bounds
        assertThat(range.start()).isEqualTo(start);
        assertThat(range.end()).isEqualTo(end);
    }

    @Test
    void accepts_a_single_day_range() {
        // GIVEN start == end (a one-day prorata window)
        LocalDate day = LocalDate.of(2026, 9, 25);

        // WHEN / THEN it is accepted
        assertThat(DateRange.of(day, day).end()).isEqualTo(day);
    }

    @Test
    void rejects_an_end_before_the_start() {
        // GIVEN an inverted range
        LocalDate start = LocalDate.of(2026, 10, 11);
        LocalDate end = LocalDate.of(2026, 9, 12);

        // WHEN / THEN construction fails fast
        assertThatThrownBy(() -> DateRange.of(start, end))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejects_null_bounds() {
        // GIVEN / WHEN / THEN null start or end is rejected
        assertThatThrownBy(() -> DateRange.of(null, LocalDate.of(2026, 9, 12)))
                .isInstanceOf(NullPointerException.class);
        assertThatThrownBy(() -> DateRange.of(LocalDate.of(2026, 9, 12), null))
                .isInstanceOf(NullPointerException.class);
    }
}
