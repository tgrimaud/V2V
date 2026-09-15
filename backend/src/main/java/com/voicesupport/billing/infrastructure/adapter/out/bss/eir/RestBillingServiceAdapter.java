package com.voicesupport.billing.infrastructure.adapter.out.bss.eir;

import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingServiceClient.InvoiceHistory;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Objects;

// RestClient-backed billing-service adapter for the account invoice list. Sends the two galaxion-user-*
// authorization headers; a 404 becomes an empty list (account/invoices not found), any other HTTP or
// transport error propagates so the global handler degrades it to a sanitized 503.
public class RestBillingServiceAdapter implements BillingServiceClient {

    private final RestClient restClient;

    public RestBillingServiceAdapter(RestClient restClient) {
        this.restClient = Objects.requireNonNull(restClient, "restClient must not be null");
    }

    @Override
    public List<InvoiceHistory> listAccountInvoices(String accountId, GalaxionUser user) {
        Objects.requireNonNull(accountId, "accountId must not be null");
        Objects.requireNonNull(user, "user must not be null");
        try {
            InvoiceHistory[] body = restClient.get()
                    .uri("/api/v1/accounts/{accountId}/invoices", accountId)
                    .header(RestBillingEnquiryAdapter.HEADER_USER_TYPE, user.userType())
                    .header(RestBillingEnquiryAdapter.HEADER_USER_IDENTIFIER, user.userIdentifier())
                    .retrieve()
                    .body(InvoiceHistory[].class);
            return body == null ? List.of() : List.of(body);
        } catch (HttpClientErrorException.NotFound notFound) {
            return List.of();
        }
    }
}
