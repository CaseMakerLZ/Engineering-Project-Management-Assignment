package com.Agent.javabackend.Service;

import com.Agent.javabackend.dto.*;
import jakarta.validation.Valid;

public interface AgentService {
    HealthResponse health();

    RunResponse getRun(String runId);

    CreateRunResponse createRun(@Valid CreateRunRequest request);

    RunMessagesResponse getMessages(String runId);

    CancelRunResponse cancelRun(String runId);
}
