package com.Agent.javabackend.Controller;

import com.Agent.javabackend.dto.*;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;

/**
 * TODO:当前的这些接口貌似有个共同的问题————它们都不是异步的，但是貌似对于前端用户的体验来讲，就是要这种效果？我还不明确
 */
@RestController
@RequestMapping("/api/agent")
public class AgentServiceController {
    private final RestClient restClient;

    public AgentServiceController(RestClient restClient){
        this.restClient =  restClient;
    }

    @GetMapping("/health")
    public Result<HealthResponse> health(){
        HealthResponse healthResponse = restClient.get()
                .uri("/api/internal/health")
                .retrieve()
                .body(HealthResponse.class);
        return Result.success(healthResponse);
    }

    //查询任务
    @GetMapping("/runs/{runId}")
    public Result<RunResponse> getRun(@PathVariable String runId){
        RunResponse runResponse = restClient.get()
                .uri("/api/internal/runs/{runId}", runId)
                .retrieve()
                .body(RunResponse.class);
        return Result.success(runResponse);
    }

    //创建任务
    @PostMapping("/runs")
    public Result<CreateRunResponse> CreateRun(@Valid @RequestBody CreateRunRequest request){
        CreateRunResponse createRunResponse = restClient.post()
                .uri("/api/internal/runs")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request).retrieve()
                .body(CreateRunResponse.class);

        return Result.success(createRunResponse);
    }

    //查询消息
    @GetMapping("/runs/{runId}/messages")
    public Result<RunMessagesResponse> getMessages(@PathVariable String runId){
        RunMessagesResponse response = restClient.get()
                .uri("/api/internal/runs/{runId}/messages", runId)
                .retrieve()
                .body(RunMessagesResponse.class);
        return Result.success(response);
    }

    //取消任务
    @PostMapping("/runs/{runId}/cancel")
    public Result<CancelRunResponse> cancelRun(@PathVariable String runId){
        CancelRunResponse response = restClient.post()
                .uri("/api/internal/runs/{runId}/cancel", runId)
                .retrieve()
                .body(CancelRunResponse.class);
        return Result.success(response);
    }
}
