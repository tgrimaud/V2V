package com.voicesupport.billing.domain.model;

// How a billed line evolved between the two compared invoices. Drives how a LineDelta is phrased
// (a line that appeared vs one whose amount changed).
public enum ChangeKind {
    APPEARED,
    DISAPPEARED,
    CHANGED,
    UNCHANGED
}
