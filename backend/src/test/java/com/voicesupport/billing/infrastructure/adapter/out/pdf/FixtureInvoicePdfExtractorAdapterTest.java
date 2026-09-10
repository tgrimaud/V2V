package com.voicesupport.billing.infrastructure.adapter.out.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.ExtractionStatus;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("FixtureInvoicePdfExtractorAdapter (ADR-0005 fallback contract)")
class FixtureInvoicePdfExtractorAdapterTest {

    private static final byte[] BYTES = "%PDF-1.7 synthetic".getBytes(StandardCharsets.UTF_8);
    private final FixtureInvoicePdfExtractorAdapter extractor =
            new FixtureInvoicePdfExtractorAdapter(BssBillingFixtures.all());

    @Test
    void extracts_a_structured_invoice_from_a_known_reference() {
        // GIVEN a PDF whose reference maps to a fixture invoice
        PdfSource source = new PdfSource("eir-001-2026-01", BYTES);

        // WHEN it is extracted
        ExtractionResult result = extractor.extract(source);

        // THEN a complete invoice is returned
        assertThat(result.status()).isEqualTo(ExtractionStatus.SUCCESS);
        assertThat(result.hasInvoice()).isTrue();
        assertThat(result.invoice().period().id()).isEqualTo("eir-001-2026-01");
        assertThat(result.issues()).isEmpty();
    }

    @Test
    void a_partial_reference_yields_a_partial_extraction_with_issues() {
        // GIVEN a reference flagged as partially readable
        PdfSource source = new PdfSource("eir-001-2026-01-partial", BYTES);

        // WHEN it is extracted
        ExtractionResult result = extractor.extract(source);

        // THEN the invoice is returned but the missing content is surfaced
        assertThat(result.status()).isEqualTo(ExtractionStatus.PARTIAL);
        assertThat(result.hasInvoice()).isTrue();
        assertThat(result.issues()).isNotEmpty();
    }

    @Test
    void an_empty_document_fails_without_an_invoice() {
        // GIVEN a document with no bytes
        PdfSource source = new PdfSource("eir-001-2026-01", new byte[0]);

        // WHEN it is extracted
        ExtractionResult result = extractor.extract(source);

        // THEN extraction fails and carries no invoice
        assertThat(result.status()).isEqualTo(ExtractionStatus.FAILED);
        assertThat(result.hasInvoice()).isFalse();
        assertThat(result.issues()).isNotEmpty();
    }

    @Test
    void an_unknown_reference_fails() {
        // GIVEN a reference that maps to no fixture invoice
        PdfSource source = new PdfSource("does-not-exist", BYTES);

        // WHEN / THEN extraction fails
        assertThat(extractor.extract(source).status()).isEqualTo(ExtractionStatus.FAILED);
    }

    @Test
    void rejects_a_null_source() {
        // GIVEN / WHEN / THEN a null source is rejected
        assertThatThrownBy(() -> extractor.extract(null)).isInstanceOf(NullPointerException.class);
    }
}
