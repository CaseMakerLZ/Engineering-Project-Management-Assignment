package com.Agent.javabackend.Client;

import com.Agent.javabackend.dto.CancelRunResponse;
import com.Agent.javabackend.dto.CreateRunRequest;
import com.Agent.javabackend.dto.CreateRunResponse;
import com.Agent.javabackend.dto.HealthResponse;
import com.Agent.javabackend.dto.RunMessagesResponse;
import com.Agent.javabackend.dto.RunResponse;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Python Agent Service 的 HTTP 通信适配器。
 *
 * 这个类只负责远程调用细节：接口路径、HTTP 方法、请求体和响应 DTO。
 * Java 业务服务不需要直接依赖 RestClient，也不需要知道 Python 的 URL 结构。
 */
@Component
public class PythonAgentClient {
    private final RestClient restClient;

    public PythonAgentClient(RestClient restClient) {
        this.restClient = restClient;
    }

    public HealthResponse health() {
        return restClient.get()
                .uri("/api/internal/health")
                .retrieve()
                .body(HealthResponse.class);
    }

    public RunResponse getRun(String runId) {
        return restClient.get()
                .uri("/api/internal/runs/{runId}", runId)
                .retrieve()
                .body(RunResponse.class);
    }

    public CreateRunResponse createRun(CreateRunRequest request) {
        return restClient.post()
                .uri("/api/internal/runs")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(CreateRunResponse.class);
    }

    public RunMessagesResponse getMessages(String runId) {
        return restClient.get()
                .uri("/api/internal/runs/{runId}/messages", runId)
                .retrieve()
                .body(RunMessagesResponse.class);
    }

    public CancelRunResponse cancelRun(String runId) {
        return restClient.post()
                .uri("/api/internal/runs/{runId}/cancel", runId)
                .retrieve()
                .body(CancelRunResponse.class);
    }
}
