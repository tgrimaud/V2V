package com.voicesupport.billing.infrastructure.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.ExtractionStatus;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceGroup;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.InvoiceSection;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.infrastructure.adapter.out.pdf.PdfBoxInvoiceExtractorAdapter;
import com.voicesupport.billing.infrastructure.fixtures.EirB2cSampleFixtures;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

// TASK-BE-065: the real goal — parsing the ACTUAL anonymized eir B2C sample PDFs (held in test
// resources) must reproduce EirB2cSampleFixtures, which were hand-transcribed from those same PDFs.
// We assert the full business structure the comparison engine consumes: identity, period windows,
// section -> group -> item tree, inferred category, prorata line periods, per-line and rolled-up
// amounts (23% VAT split). We do NOT assert synthetic enrichment absent from the PDF (section/group/
// item ids, line codes, evidence source) nor the exact label wording (the fixtures paraphrased some
// labels — the parser keeps the verbatim PDF text, which is strictly more faithful).
class EirB2cRealPdfParsingTest {

    private final PdfBoxInvoiceExtractorAdapter adapter =
            new PdfBoxInvoiceExtractorAdapter(new EirB2cInvoiceLayoutParser());

    @Test
    void parsingTheRealEirB2cSamplePdfsReproducesTheTranscribedFixtures() throws IOException {
        // GIVEN the three real accounts transcribed from the anonymized eir B2C PDFs (Aug + Sep each)
        Map<AccountId, List<Invoice>> fixtures = EirB2cSampleFixtures.all();

        for (Map.Entry<AccountId, List<Invoice>> entry : fixtures.entrySet()) {
            String account = entry.getKey().value();
            List<Invoice> invoices = entry.getValue();
            for (int month = 0; month < invoices.size(); month++) {
                Invoice expected = invoices.get(month);
                byte[] pdf = readPdf(account, month == 0 ? "20260812" : "20260912");

                // WHEN the real PDF is parsed by the eir B2C layout parser
                ExtractionResult result = adapter.extract(new PdfSource(expected.id().value(), pdf));

                // THEN it reconciles and reproduces the transcribed invoice structure + amounts
                assertEquals(ExtractionStatus.SUCCESS, result.status(), "status for " + expected.id().value());
                assertInvoiceEquivalent(expected, result.invoice());
            }
        }
    }

    private static void assertInvoiceEquivalent(Invoice expected, Invoice parsed) {
        String id = expected.id().value();
        assertEquals(expected.id().value(), parsed.id().value(), "invoice id");
        assertEquals(expected.accountId().value(), parsed.accountId().value(), "account " + id);
        assertEquals(expected.level(), parsed.level(), "level " + id);
        assertEquals(expected.period().id(), parsed.period().id(), "period id " + id);
        assertEquals(expected.period().invoiceDate(), parsed.period().invoiceDate(), "invoice date " + id);
        assertEquals(expected.period().usagePeriod(), parsed.period().usagePeriod(), "usage period " + id);
        assertEquals(expected.period().chargePeriod(), parsed.period().chargePeriod(), "charge period " + id);
        assertAmounts(expected.totals(), parsed.totals(), "invoice totals " + id);

        assertEquals(expected.sections().size(), parsed.sections().size(), "section count " + id);
        for (int s = 0; s < expected.sections().size(); s++) {
            assertSectionEquivalent(expected.sections().get(s), parsed.sections().get(s), id);
        }
    }

    private static void assertSectionEquivalent(InvoiceSection expected, InvoiceSection parsed, String id) {
        String where = id + " / section '" + expected.name() + "'";
        assertEquals(expected.name(), parsed.name(), "section name " + where);
        assertEquals(expected.displayOrder(), parsed.displayOrder(), "section order " + where);
        assertEquals(expected.inDetails(), parsed.inDetails(), "section inDetails " + where);
        assertAmounts(expected.amounts(), parsed.amounts(), "section amounts " + where);
        assertEquals(expected.groups().size(), parsed.groups().size(), "group count " + where);
        for (int g = 0; g < expected.groups().size(); g++) {
            assertGroupEquivalent(expected.groups().get(g), parsed.groups().get(g), where);
        }
    }

    private static void assertGroupEquivalent(InvoiceGroup expected, InvoiceGroup parsed, String where) {
        String groupWhere = where + " / group '" + expected.name() + "'";
        assertEquals(expected.name(), parsed.name(), "group name " + groupWhere);
        assertEquals(expected.period(), parsed.period(), "group period " + groupWhere);
        assertAmounts(expected.amounts(), parsed.amounts(), "group amounts " + groupWhere);
        assertEquals(expected.items().size(), parsed.items().size(), "item count " + groupWhere);
        for (int i = 0; i < expected.items().size(); i++) {
            assertItemEquivalent(expected.items().get(i), parsed.items().get(i), groupWhere, i);
        }
    }

    private static void assertItemEquivalent(InvoiceItem expected, InvoiceItem parsed, String where, int i) {
        String itemWhere = where + " / item[" + i + "]";
        assertEquals(expected.category(), parsed.category(), "category " + itemWhere);
        assertEquals(expected.period(), parsed.period(), "line period " + itemWhere);
        assertAmounts(expected.amounts(), parsed.amounts(), "amounts " + itemWhere);
    }

    private static void assertAmounts(LineAmounts expected, LineAmounts parsed, String where) {
        assertEquals(expected.taxIncluded().minorUnits(), parsed.taxIncluded().minorUnits(), "TTC " + where);
        assertEquals(expected.taxExcluded().minorUnits(), parsed.taxExcluded().minorUnits(), "HT " + where);
        assertEquals(expected.tax().minorUnits(), parsed.tax().minorUnits(), "VAT " + where);
    }

    private static byte[] readPdf(String account, String dateTag) throws IOException {
        String resource = "/billing/eir-b2c/" + account + "_EIR_MOBILE_TEST_" + dateTag + "_B2C.pdf";
        try (InputStream in = EirB2cRealPdfParsingTest.class.getResourceAsStream(resource)) {
            assertNotNull(in, "missing test resource " + resource);
            return in.readAllBytes();
        }
    }
}
