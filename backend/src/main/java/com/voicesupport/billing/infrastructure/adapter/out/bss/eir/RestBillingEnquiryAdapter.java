package com.voicesupport.billing.infrastructure.adapter.out.bss.eir;

import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.InvoiceResponse;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import java.util.Objects;
import java.util.Optional;

// RestClient-backed billing-enquiry-service adapter. Sends the two galaxion-user-* authorization
// headers on every call; a 404 becomes an empty Optional (invoice not found), any other HTTP or
// transport error propagates so the global handler degrades it to a sanitized 503.
public class RestBillingEnquiryAdapter implements BillingEnquiryClient {

    static final String HEADER_USER_TYPE = "galaxion-user-type";
    static final String HEADER_USER_IDENTIFIER = "galaxion-user-identifier";

    private final RestClient restClient;

    public RestBillingEnquiryAdapter(RestClient restClient) {
        this.restClient = Objects.requireNonNull(restClient, "restClient must not be null");
    }

    @Override
    public Optional<InvoiceResponse> fetchInvoice(long invoiceId, GalaxionUser user) {
        Objects.requireNonNull(user, "user must not be null");
        try {
            return Optional.ofNullable(restClient.get()
                    .uri("/billing-enquiry/invoices/{invoiceId}", invoiceId)
                    .header(HEADER_USER_TYPE, user.userType())
                    .header(HEADER_USER_IDENTIFIER, user.userIdentifier())
                    .retrieve()
                    .body(InvoiceResponse.class));
        } catch (HttpClientErrorException.NotFound notFound) {
            return Optional.empty();
        }
    }
}
