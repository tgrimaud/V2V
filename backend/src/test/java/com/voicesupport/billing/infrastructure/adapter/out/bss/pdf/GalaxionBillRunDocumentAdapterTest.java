package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GalaxionBillRunDocumentAdapterTest {

    private static final GalaxionUser USER = new GalaxionUser("SYSTEM", "SYSTEM");
    private static final AccountId ACCOUNT = AccountId.of("99224964");
    private static final InvoiceId INVOICE = InvoiceId.of("113444");

    private GalaxionBillRunDocumentAdapter adapterWith(FakeBillRunDocumentClient client) {
        return new GalaxionBillRunDocumentAdapter(client, USER);
    }

    @Test
    void download_searchesByAccountAndInvoiceThenDownloadsTheDocumentBytes() {
        // GIVEN the search returns one document and its download yields PDF bytes
        byte[] pdf = "%PDF-1.4 invoice".getBytes(StandardCharsets.UTF_8);
        FakeBillRunDocumentClient client = new FakeBillRunDocumentClient();
        client.searchResult = List.of(new BillRunDocumentClient.BillRunDocument("doc-uuid-1", "inv.pdf", "application/pdf"));
        client.downloadResult = Optional.of(pdf);
        GalaxionBillRunDocumentAdapter adapter = adapterWith(client);

        // WHEN the invoice PDF is downloaded
        Optional<PdfSource> source = adapter.download(ACCOUNT, INVOICE);

        // THEN the bytes come back referenced by the document id, and the account/invoice/user reach the client
        assertTrue(source.isPresent());
        assertEquals("doc-uuid-1", source.get().reference());
        assertArrayEquals(pdf, source.get().content());
        assertEquals("99224964", client.lastCriteria.accountId());
        assertEquals("113444", client.lastCriteria.invoiceNumber());
        assertEquals("doc-uuid-1", client.lastDownloadDocumentId);
        assertEquals(USER, client.lastSearchUser);
        assertEquals(USER, client.lastDownloadUser);
    }

    @Test
    void download_isEmptyWhenNoDocumentMatchesTheSearch() {
        // GIVEN the search returns no document
        FakeBillRunDocumentClient client = new FakeBillRunDocumentClient();
        client.searchResult = List.of();

        // WHEN the invoice PDF is downloaded THEN nothing is returned and no download is attempted
        assertTrue(adapterWith(client).download(ACCOUNT, INVOICE).isEmpty());
        assertNull(client.lastDownloadDocumentId);
    }

    @Test
    void download_isEmptyWhenTheDocumentDownloadReturnsNothing() {
        // GIVEN a document is found but its download is empty (404 -> Optional.empty)
        FakeBillRunDocumentClient client = new FakeBillRunDocumentClient();
        client.searchResult = List.of(new BillRunDocumentClient.BillRunDocument("doc-uuid-2", "inv.pdf", "application/pdf"));
        client.downloadResult = Optional.empty();

        // WHEN the invoice PDF is downloaded THEN nothing is returned (fail-closed)
        assertTrue(adapterWith(client).download(ACCOUNT, INVOICE).isEmpty());
    }

    @Test
    void download_isEmptyWhenTheDownloadedDocumentHasZeroBytes() {
        // GIVEN a document is found but the download yields empty bytes
        FakeBillRunDocumentClient client = new FakeBillRunDocumentClient();
        client.searchResult = List.of(new BillRunDocumentClient.BillRunDocument("doc-uuid-3", "inv.pdf", "application/pdf"));
        client.downloadResult = Optional.of(new byte[0]);

        // WHEN the invoice PDF is downloaded THEN an empty document is treated as unusable (fail-closed)
        assertTrue(adapterWith(client).download(ACCOUNT, INVOICE).isEmpty());
    }

    @Test
    void download_skipsBlankDocumentIdsAndTakesTheFirstUsableMatch() {
        // GIVEN the search returns a blank id first, then a usable one
        byte[] pdf = "bytes".getBytes(StandardCharsets.UTF_8);
        FakeBillRunDocumentClient client = new FakeBillRunDocumentClient();
        client.searchResult = List.of(
                new BillRunDocumentClient.BillRunDocument(" ", "blank.pdf", "application/pdf"),
                new BillRunDocumentClient.BillRunDocument("doc-uuid-4", "inv.pdf", "application/pdf"));
        client.downloadResult = Optional.of(pdf);

        // WHEN the invoice PDF is downloaded THEN the first non-blank document id is used
        Optional<PdfSource> source = adapterWith(client).download(ACCOUNT, INVOICE);
        assertTrue(source.isPresent());
        assertEquals("doc-uuid-4", client.lastDownloadDocumentId);
    }

    @Test
    void listDocuments_isFailClosedEmptyBecauseSearchLacksPeriodAndAmount() {
        // GIVEN a search would return documents, but they carry no period/amount (missing-inputs.md)
        FakeBillRunDocumentClient client = new FakeBillRunDocumentClient();
        client.searchResult = List.of(new BillRunDocumentClient.BillRunDocument("doc-uuid-5", "inv.pdf", "application/pdf"));

        // WHEN the account documents are listed THEN the adapter fail-closes to empty (no fabricated summary)
        List<InvoiceSummary> summaries = adapterWith(client).listDocuments(ACCOUNT);
        assertTrue(summaries.isEmpty());
    }

    // Manual fake of the HTTP seam (no Mockito): records the last search criteria / download id and the
    // galaxion user so the adapter's search->download wiring and header passthrough can be asserted.
    private static final class FakeBillRunDocumentClient implements BillRunDocumentClient {

        private List<BillRunDocument> searchResult = List.of();
        private Optional<byte[]> downloadResult = Optional.empty();
        private DocumentSearchCriteria lastCriteria;
        private GalaxionUser lastSearchUser;
        private String lastDownloadDocumentId;
        private GalaxionUser lastDownloadUser;

        @Override
        public List<BillRunDocument> search(DocumentSearchCriteria criteria, GalaxionUser user) {
            this.lastCriteria = criteria;
            this.lastSearchUser = user;
            return searchResult;
        }

        @Override
        public Optional<byte[]> download(String documentId, String billPeriodId, GalaxionUser user) {
            this.lastDownloadDocumentId = documentId;
            this.lastDownloadUser = user;
            return downloadResult;
        }
    }
}
