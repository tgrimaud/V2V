package com.voicesupport.domain.port.in;

import com.voicesupport.domain.model.billing.Invoice;
import com.voicesupport.domain.model.billing.InvoiceComparison;

public interface CompareInvoicesUseCase {

    InvoiceComparison compare(Invoice previous, Invoice current);
}
