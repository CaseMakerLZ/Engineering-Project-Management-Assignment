package com.Agent.javabackend.Service.impl;


import com.Agent.javabackend.Client.PythonAgentClient;
import com.Agent.javabackend.Service.AgentService;
import com.Agent.javabackend.dto.*;
import org.springframework.stereotype.Service;

@Service
public class AgentServiceImpl implements AgentService {
    private final PythonAgentClient pythonAgentClient;

    public AgentServiceImpl(PythonAgentClient pythonAgentClient) {
        this.pythonAgentClient = pythonAgentClient;
    }


    @Override
    public HealthResponse health() {
        return pythonAgentClient.health();
    }

    @Override
    public RunResponse getRun(String runId) {
        return pythonAgentClient.getRun(runId);
    }

    @Override
    public CreateRunResponse createRun(CreateRunRequest request) {
        return pythonAgentClient.createRun(request);
    }

    @Override
    public RunMessagesResponse getMessages(String runId) {
        return pythonAgentClient.getMessages(runId);
    }

    @Override
    public CancelRunResponse cancelRun(String runId) {
        return pythonAgentClient.cancelRun(runId);
    }


}
