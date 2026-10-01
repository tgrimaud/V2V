package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriBuilder;

import java.util.List;
import java.util.Objects;
import java.util.Optional;

// RestClient-backed `bill-run-documents` client (TASK-BE-063). Sends the two galaxion-user-*
// authorization headers on every call (same contract as the Eir adapters); a 404 becomes an empty
// result (document not found), any other HTTP or transport error propagates so the global handler
// degrades it to a sanitized 503. Thin HTTP mapping only — the search->download->fail-closed logic
// lives in GalaxionBillRunDocumentAdapter (unit-tested through a fake of this seam), mirroring how
// RestBillingEnquiryAdapter stays an untested thin mapping behind BillingEnquiryClient.
public class RestBillRunDocumentAdapter implements BillRunDocumentClient {

    static final String HEADER_USER_TYPE = "galaxion-user-type";
    static final String HEADER_USER_IDENTIFIER = "galaxion-user-identifier";

    private static final String SEARCH_PATH = "/bill-run-documents/search";
    private static final String DOWNLOAD_PATH = "/bill-run-documents/{documentId}/download";

    private final RestClient restClient;

    public RestBillRunDocumentAdapter(RestClient restClient) {
        this.restClient = Objects.requireNonNull(restClient, "restClient must not be null");
    }

    @Override
    public List<BillRunDocument> search(DocumentSearchCriteria criteria, GalaxionUser user) {
        Objects.requireNonNull(criteria, "criteria must not be null");
        Objects.requireNonNull(user, "user must not be null");
        try {
            BillRunDocument[] body = restClient.get()
                    .uri(uriBuilder -> searchUri(uriBuilder, criteria))
                    .header(HEADER_USER_TYPE, user.userType())
                    .header(HEADER_USER_IDENTIFIER, user.userIdentifier())
                    .retrieve()
                    .body(BillRunDocument[].class);
            return body == null ? List.of() : List.of(body);
        } catch (HttpClientErrorException.NotFound notFound) {
            return List.of();
        }
    }

    @Override
    public Optional<byte[]> download(String documentId, String billPeriodId, GalaxionUser user) {
        Objects.requireNonNull(documentId, "documentId must not be null");
        Objects.requireNonNull(user, "user must not be null");
        try {
            byte[] body = restClient.get()
                    .uri(uriBuilder -> downloadUri(uriBuilder, documentId, billPeriodId))
                    .header(HEADER_USER_TYPE, user.userType())
                    .header(HEADER_USER_IDENTIFIER, user.userIdentifier())
                    .retrieve()
                    .body(byte[].class);
            return Optional.ofNullable(body);
        } catch (HttpClientErrorException.NotFound notFound) {
            return Optional.empty();
        }
    }

    private static java.net.URI searchUri(UriBuilder builder, DocumentSearchCriteria criteria) {
        builder.path(SEARCH_PATH);
        addParam(builder, "billRunAccountId", criteria.billRunAccountId());
        addParam(builder, "accountId", criteria.accountId());
        addParam(builder, "invoiceNumber", criteria.invoiceNumber());
        addParam(builder, "billPeriodId", criteria.billPeriodId());
        return builder.build();
    }

    private static java.net.URI downloadUri(UriBuilder builder, String documentId, String billPeriodId) {
        builder.path(DOWNLOAD_PATH);
        addParam(builder, "billPeriodId", billPeriodId);
        return builder.build(documentId);
    }

    private static void addParam(UriBuilder builder, String name, String value) {
        if (value != null && !value.isBlank()) {
            builder.queryParam(name, value);
        }
    }
}
