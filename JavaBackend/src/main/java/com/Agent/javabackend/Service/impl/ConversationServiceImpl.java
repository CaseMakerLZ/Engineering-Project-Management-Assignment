package com.Agent.javabackend.Service.impl;

import com.Agent.javabackend.Client.PythonAgentClient;
import com.Agent.javabackend.Service.ConversationService;
import com.Agent.javabackend.Service.ProjectService;
import com.Agent.javabackend.dto.CreateRunRequest;
import com.Agent.javabackend.dto.CreateRunResponse;
import com.Agent.javabackend.dto.RunResponse;
import com.Agent.javabackend.dto.RunStatus;
import com.Agent.javabackend.dto.ConversationDTO.*;
import com.Agent.javabackend.entity.MessageContainer.AgentTask;
import com.Agent.javabackend.entity.MessageContainer.Conversation;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Service
public class ConversationServiceImpl implements ConversationService {
    private final ProjectService projectService;
    private final PythonAgentClient pythonAgentClient;
    // 当前 Java 数据库尚未启用。这些数据暂存服务器内存，进程重启即清空。
    private final ConcurrentMap<String, Conversation> conversations = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, AgentTask> tasks = new ConcurrentHashMap<>();

    public ConversationServiceImpl(ProjectService projectService, PythonAgentClient pythonAgentClient) {
        this.projectService = projectService;
        this.pythonAgentClient = pythonAgentClient;
    }

    @Override
    public ConversationResponse create(String projectId, CreateConversationRequest request) {
        projectService.get(projectId);
        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID().toString());
        conversation.setProjectId(projectId);
        conversation.setTitle(request.getTitle());
        conversation.setStatus("ACTIVE");
        conversation.setCreatedAt(now);
        conversation.setUpdatedAt(now);
        conversations.put(conversation.getId(), conversation);
        return toResponse(conversation);
    }

    @Override
    public ConversationResponse get(String conversationId) {
        return toResponse(requireConversation(conversationId));
    }

    @Override
    public List<ConversationResponse> list(String projectId) {
        projectService.get(projectId);
        return conversations.values().stream()
                .filter(conversation -> projectId.equals(conversation.getProjectId()))
                .sorted(Comparator.comparing(Conversation::getCreatedAt))
                .map(this::toResponse).toList();
    }

    @Override
    public synchronized CreateTurnResponse createTurn(String conversationId, CreateTurnRequest request) {
        Conversation conversation = requireConversation(conversationId);
        List<AgentTask> previous = orderedTasks(conversationId);
        for (AgentTask task : previous) {
            refresh(task);
            if ("CREATED".equals(task.getStatus()) || "RUNNING".equals(task.getStatus())) {
                throw new BaseException(ErrorCode.CONVERSATION_STATE_CONFLICT);
            }
        }

        List<ContextMessage> context = new ArrayList<>();
        for (AgentTask task : previous) {
            if ("COMPLETED".equals(task.getStatus()) && task.getResult() != null) {
                context.add(new ContextMessage("user", task.getPrompt()));
                context.add(new ContextMessage("assistant", task.getResult()));
            }
        }
        // Python 接口限制最多 20 条上下文消息，即最近 10 个已完成的 Turn。
        if (context.size() > 20) context = new ArrayList<>(context.subList(context.size() - 20, context.size()));

        AgentTask task = new AgentTask();
        task.setId(UUID.randomUUID().toString());
        task.setConversationId(conversationId);
        task.setPrompt(request.getPrompt());
        task.setStatus("CREATED");
        task.setCreatedAt(OffsetDateTime.now(ZoneOffset.UTC));

        CreateRunRequest runRequest = new CreateRunRequest(conversation.getProjectId(), request.getPrompt());
        runRequest.setConversationId(conversationId);
        runRequest.setContext(context);
        CreateRunResponse run = pythonAgentClient.createRun(runRequest);
        task.setPythonRunId(run.getRunId());
        task.setStatus(run.getStatus().name());
        tasks.put(task.getId(), task);
        return new CreateTurnResponse(task.getId(), conversationId, task.getPythonRunId(), task.getStatus());
    }

    @Override
    public TurnResponse getTurn(String conversationId, String taskId) {
        requireConversation(conversationId);
        AgentTask task = tasks.get(taskId);
        if (task == null || !conversationId.equals(task.getConversationId())) throw new BaseException(ErrorCode.AGENT_TASK_NOT_FOUND);
        refresh(task);
        return toResponse(task);
    }

    @Override
    public List<TurnResponse> listTurns(String conversationId) {
        requireConversation(conversationId);
        List<AgentTask> ordered = orderedTasks(conversationId);
        ordered.forEach(this::refresh);
        return ordered.stream().map(this::toResponse).toList();
    }

    private void refresh(AgentTask task) {
        if (!"CREATED".equals(task.getStatus()) && !"RUNNING".equals(task.getStatus())) return;
        RunResponse run = pythonAgentClient.getRun(task.getPythonRunId());
        task.setStatus(run.getStatus().name());
        task.setResult(run.getResult());
        task.setError(run.getError());
        task.setStartedAt(run.getStartedAt());
        task.setFinishedAt(run.getFinishedAt());
    }

    private List<AgentTask> orderedTasks(String conversationId) {
        return tasks.values().stream().filter(task -> conversationId.equals(task.getConversationId()))
                .sorted(Comparator.comparing(AgentTask::getCreatedAt)).toList();
    }

    private Conversation requireConversation(String conversationId) {
        Conversation conversation = conversations.get(conversationId);
        if (conversation == null) throw new BaseException(ErrorCode.CONVERSATION_NOT_FOUND);
        return conversation;
    }

    private ConversationResponse toResponse(Conversation conversation) {
        ConversationResponse response = new ConversationResponse();
        response.setConversationId(conversation.getId());
        response.setProjectId(conversation.getProjectId());
        response.setTitle(conversation.getTitle());
        response.setStatus(conversation.getStatus());
        response.setCreatedAt(conversation.getCreatedAt());
        response.setUpdatedAt(conversation.getUpdatedAt());
        return response;
    }

    private TurnResponse toResponse(AgentTask task) {
        TurnResponse response = new TurnResponse();
        response.setTaskId(task.getId());
        response.setConversationId(task.getConversationId());
        response.setPythonRunId(task.getPythonRunId());
        response.setPrompt(task.getPrompt());
        response.setStatus(task.getStatus());
        response.setResult(task.getResult());
        response.setError(task.getError());
        response.setCreatedAt(task.getCreatedAt());
        response.setStartedAt(task.getStartedAt());
        response.setFinishedAt(task.getFinishedAt());
        return response;
    }
}
