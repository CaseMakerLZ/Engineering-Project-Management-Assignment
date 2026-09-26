package com.Agent.javabackend.Controller;

import com.Agent.javabackend.Service.AgentService;
import com.Agent.javabackend.dto.*;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

/**
 * TODO:当前的这些接口貌似有个共同的问题————它们都不是异步的，但是貌似对于前端用户的体验来讲，就是要这种效果？我还不明确
 */
@RestController
@RequestMapping("/api/agent")
public class AgentServiceController {
    private final AgentService agentService;

    public AgentServiceController(AgentService agentService){
        this.agentService = agentService;
    }

    @GetMapping("/health")
    public Result<HealthResponse> health(){
        HealthResponse healthResponse = agentService.health();
        return Result.success(healthResponse);
    }

    //查询任务
    @GetMapping("/runs/{runId}")
    public Result<RunResponse> getRun(@PathVariable String runId){
        RunResponse runResponse = agentService.getRun(runId);
        return Result.success(runResponse);
    }

    //创建任务
    @PostMapping("/runs")
    public Result<CreateRunResponse> createRun(@Valid @RequestBody CreateRunRequest request){
        CreateRunResponse createRunResponse = agentService.createRun(request);
        return Result.success(createRunResponse);
    }

    //查询消息
    @GetMapping("/runs/{runId}/messages")
    public Result<RunMessagesResponse> getMessages(@PathVariable String runId){
        RunMessagesResponse response = agentService.getMessages(runId);
        return Result.success(response);
    }

    //取消任务
    @PostMapping("/runs/{runId}/cancel")
    public Result<CancelRunResponse> cancelRun(@PathVariable String runId){
        CancelRunResponse response = agentService.cancelRun(runId);
        return Result.success(response);
    }
}
