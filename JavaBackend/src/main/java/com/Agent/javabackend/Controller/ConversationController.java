package com.Agent.javabackend.Controller;

import com.Agent.javabackend.Service.ConversationService;
import com.Agent.javabackend.Service.TurnEventService;
import com.Agent.javabackend.auth.AuthPrincipal;
import com.Agent.javabackend.dto.ConversationDTO.*;
import com.Agent.javabackend.dto.Result;
import com.Agent.javabackend.entity.MessageContainer.AgentTask;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import jakarta.validation.Valid;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class ConversationController {
    private final ConversationService conversationService;
    private final TurnEventService turnEventService;

    public ConversationController(ConversationService conversationService,
                                  TurnEventService turnEventService) {
        this.conversationService = conversationService;
        this.turnEventService = turnEventService;
    }

    @PostMapping("/projects/{projectId}/conversations")
    public Result<ConversationResponse> create(
            @PathVariable String projectId,
            @Valid @RequestBody CreateConversationRequest request,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        return Result.success(conversationService.create(projectId, request, ownerId(principal)));
    }

    @GetMapping("/conversations/{conversationId}")
    public Result<ConversationResponse> get(
            @PathVariable String conversationId,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        return Result.success(conversationService.get(conversationId, ownerId(principal)));
    }

    @GetMapping("/projects/{projectId}/conversations")
    public Result<java.util.List<ConversationResponse>> list(
            @PathVariable String projectId,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        return Result.success(conversationService.list(projectId, ownerId(principal)));
    }
    @PostMapping("/conversations/{conversationId}/turns")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Result<CreateTurnResponse> createTurn(
            @PathVariable String conversationId,
            @Valid @RequestBody CreateTurnRequest request,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        return Result.success(conversationService.createTurn(
                conversationId, request, ownerId(principal)));
    }

    @GetMapping("/conversations/{conversationId}/turns/{taskId}")
    public Result<TurnResponse> getTurn(
            @PathVariable String conversationId,
            @PathVariable String taskId,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        return Result.success(conversationService.getTurn(
                conversationId, taskId, ownerId(principal)));
    }

    @GetMapping("/conversations/{conversationId}/turns")
    public Result<java.util.List<TurnResponse>> listTurns(
            @PathVariable String conversationId,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        return Result.success(conversationService.listTurns(conversationId, ownerId(principal)));
    }

    /**
     * 转发 Python 已有的运行事件。认证和 conversation/task/project 归属检查
     * 都在当前请求线程完成，后台读取线程不再从请求里猜用户。
     */
    @GetMapping(path = "/conversations/{conversationId}/turns/{taskId}/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(
            @PathVariable String conversationId,
            @PathVariable String taskId,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal,
            HttpServletResponse response) {
        AgentTask task = conversationService.requireOwnedTask(
                conversationId, taskId, ownerId(principal));
        if (task.getPythonRunId() == null || task.getPythonRunId().isBlank()) {
            throw new BaseException(ErrorCode.AGENT_TASK_NOT_FOUND);
        }
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache");
        response.setHeader("X-Accel-Buffering", "no");
        return turnEventService.open(
                principal == null ? null : principal.sessionId(),
                principal == null ? null : principal.expiresAt(),
                conversationId,
                taskId,
                task.getPythonRunId());
    }

    private String ownerId(AuthPrincipal principal) {
        return principal == null || principal.user() == null ? null : principal.user().getUserId();
    }
}
