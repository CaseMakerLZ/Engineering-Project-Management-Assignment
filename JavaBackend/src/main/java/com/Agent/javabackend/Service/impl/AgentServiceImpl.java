package com.Agent.javabackend.Service.impl;


import com.Agent.javabackend.Service.AgentService;
import com.Agent.javabackend.dto.*;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class AgentServiceImpl implements AgentService {
    private final RestClient restClient;
    public AgentServiceImpl(RestClient restClient){
        this.restClient =  restClient;
    }


    @Override
    public HealthResponse health() {
        HealthResponse healthResponse = restClient.get()
                .uri("/api/internal/health")
                .retrieve()
                .body(HealthResponse.class);
        return healthResponse;
    }

    @Override
    public RunResponse getRun(String runId) {
        RunResponse runResponse = restClient.get()
                .uri("/api/internal/runs/{runId}", runId)
                .retrieve()
                .body(RunResponse.class);
        return runResponse;
    }

    @Override
    public CreateRunResponse createRun(CreateRunRequest request) {
        CreateRunResponse createRunResponse = restClient.post()
                .uri("/api/internal/runs")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request).retrieve()
                .body(CreateRunResponse.class);
        return createRunResponse;
    }

    @Override
    public RunMessagesResponse getMessages(String runId) {
        RunMessagesResponse response = restClient.get()
                .uri("/api/internal/runs/{runId}/messages", runId)
                .retrieve()
                .body(RunMessagesResponse.class);
        return response;
    }

    @Override
    public CancelRunResponse cancelRun(String runId) {
        CancelRunResponse response = restClient.post()
                .uri("/api/internal/runs/{runId}/cancel", runId)
                .retrieve()
                .body(CancelRunResponse.class);
        return response;
    }


}
