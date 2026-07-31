package com.voicesupport.conversation.domain.port.in;

import com.voicesupport.conversation.domain.model.valueobject.WarmUpResult;

public interface WarmUpUseCase {

    WarmUpResult warmUp();
}
