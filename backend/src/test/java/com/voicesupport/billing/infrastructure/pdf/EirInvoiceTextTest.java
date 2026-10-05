package com.voicesupport.billing.infrastructure.pdf;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

// Locks the EirInvoiceText.slug contract that gives each parsed line a stable, invoice-unique code
// (BUG-028): the same product label yields the same slug across months, while a prorata/one-off label
// (with embedded dates) yields a distinct slug and never collides with the recurring product.
class EirInvoiceTextTest {

    @Test
    void slugs_a_product_label_into_a_stable_lowercase_key() {
        // GIVEN / WHEN / THEN a plain product label becomes a hyphenated lowercase slug
        assertThat(EirInvoiceText.slug("15GB Bundle")).isEqualTo("15gb-bundle");
        assertThat(EirInvoiceText.slug("eir Mobile Connect - 30 Day")).isEqualTo("eir-mobile-connect-30-day");
        assertThat(EirInvoiceText.slug("eir Mobile Security")).isEqualTo("eir-mobile-security");
    }

    @Test
    void strips_symbols_quotes_and_edge_separators() {
        // GIVEN a label with a currency symbol, an apostrophe and leading/trailing noise
        // WHEN slugged
        // THEN only alphanumerics survive and the slug has no leading/trailing hyphen
        assertThat(EirInvoiceText.slug("€10 discount for 12 months ends August '27"))
                .isEqualTo("10-discount-for-12-months-ends-august-27");
        assertThat(EirInvoiceText.slug("  ***  ")).isEmpty();
    }

    @Test
    void a_prorata_label_with_dates_does_not_collide_with_the_recurring_product() {
        // GIVEN the recurring "15GB Bundle" and its dated prorata variant
        String recurring = EirInvoiceText.slug("15GB Bundle");
        String prorata = EirInvoiceText.slug("15GB Bundle from 25 Sep 26 until 11 Oct 26");

        // THEN they produce distinct keys so the comparison keeps them apart
        assertThat(prorata).isNotEqualTo(recurring).startsWith("15gb-bundle-from-25-sep-26");
    }

    @Test
    void null_and_blank_labels_slug_to_empty() {
        // GIVEN / WHEN / THEN null and blank labels are handled defensively
        assertThat(EirInvoiceText.slug(null)).isEmpty();
        assertThat(EirInvoiceText.slug("   ")).isEmpty();
    }
}
