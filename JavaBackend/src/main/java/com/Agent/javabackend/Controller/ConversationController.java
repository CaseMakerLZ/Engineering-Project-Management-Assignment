package com.Agent.javabackend.Controller;

import com.Agent.javabackend.Service.ConversationService;
import com.Agent.javabackend.dto.ConversationDTO.*;
import com.Agent.javabackend.dto.Result;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class ConversationController {
    private final ConversationService conversationService;

    public ConversationController(ConversationService conversationService) {
        this.conversationService = conversationService;
    }

    @PostMapping("/projects/{projectId}/conversations")
    public Result<ConversationResponse> create(
            @PathVariable String projectId, @Valid @RequestBody CreateConversationRequest request) {
        return Result.success(conversationService.create(projectId, request));
    }

    @GetMapping("/conversations/{conversationId}")
    public Result<ConversationResponse> get(@PathVariable String conversationId) {
        return Result.success(conversationService.get(conversationId));
    }

    @GetMapping("/projects/{projectId}/conversations")
    public Result<java.util.List<ConversationResponse>> list(@PathVariable String projectId) {
        return Result.success(conversationService.list(projectId));
    }
    @PostMapping("/conversations/{conversationId}/turns")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Result<CreateTurnResponse> createTurn(
            @PathVariable String conversationId, @Valid @RequestBody CreateTurnRequest request) {
        return Result.success(conversationService.createTurn(conversationId, request));
    }

    @GetMapping("/conversations/{conversationId}/turns/{taskId}")
    public Result<TurnResponse> getTurn(@PathVariable String conversationId, @PathVariable String taskId) {
        return Result.success(conversationService.getTurn(conversationId, taskId));
    }

    @GetMapping("/conversations/{conversationId}/turns")
    public Result<java.util.List<TurnResponse>> listTurns(@PathVariable String conversationId) {
        return Result.success(conversationService.listTurns(conversationId));
    }
}
