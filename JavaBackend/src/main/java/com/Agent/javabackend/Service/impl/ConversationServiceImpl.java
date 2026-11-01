package com.Agent.javabackend.Service.impl;

import com.Agent.javabackend.Client.PythonAgentClient;
import com.Agent.javabackend.Mapper.AgentTaskMapper;
import com.Agent.javabackend.Mapper.ConversationMapper;
import com.Agent.javabackend.Service.ConversationLockRegistry;
import com.Agent.javabackend.Service.ConversationService;
import com.Agent.javabackend.Service.ProjectService;
import com.Agent.javabackend.dto.CreateRunRequest;
import com.Agent.javabackend.dto.RunStatusResponse;
import com.Agent.javabackend.dto.ConversationDTO.*;
import com.Agent.javabackend.entity.MessageContainer.AgentTask;
import com.Agent.javabackend.entity.MessageContainer.Conversation;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
public class ConversationServiceImpl implements ConversationService {
    private final ProjectService projectService;
    private final PythonAgentClient pythonAgentClient;
    private final ConversationMapper conversationMapper;
    private final AgentTaskMapper agentTaskMapper;
    private final ConversationLockRegistry lockRegistry;

    public ConversationServiceImpl(ProjectService projectService, PythonAgentClient pythonAgentClient,
                                   ConversationMapper conversations, AgentTaskMapper tasks,
                                   ConversationLockRegistry lockRegistry) {
        this.projectService = projectService;
        this.pythonAgentClient = pythonAgentClient;
        this.conversationMapper = conversations;
        this.agentTaskMapper = tasks;
        this.lockRegistry = lockRegistry;
    }

    @Override
    public ConversationResponse create(String projectId, CreateConversationRequest request, String ownerId) {
        // 对话必须归属于当前用户可访问的项目。
        projectService.requireOwnedProject(projectId, ownerId);
        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID().toString());
        conversation.setProjectId(projectId);
        conversation.setTitle(request.getTitle());
        conversation.setStatus("ACTIVE");
        conversation.setCreatedAt(now);
        conversation.setUpdatedAt(now);
        conversationMapper.insert(conversation);
        return toResponse(conversation);
    }

    @Override
    public ConversationResponse get(String conversationId, String ownerId) {
        return toResponse(requireOwnedConversation(conversationId, ownerId));
    }

    @Override
    public List<ConversationResponse> list(String projectId, String ownerId) {
        projectService.requireOwnedProject(projectId, ownerId);
        return conversationMapper.findByProjectId(projectId).stream()
                .map(this::toResponse).toList();
    }
/** ==================================此线以上为conversation相关，此线以下(除了private方法)全与Turn有关========================================================*/
    @Override
    public CreateTurnResponse createTurn(
            String conversationId, CreateTurnRequest request, String ownerId) {
        // 只锁同一个对话，避免一个慢项目阻塞其他对话或其他用户。
        return lockRegistry.withLock(conversationId,
                () -> createTurnLocked(conversationId, request, ownerId));
    }

    private CreateTurnResponse createTurnLocked(
            String conversationId, CreateTurnRequest request, String ownerId) {
        Conversation conversation = requireOwnedConversation(conversationId, ownerId);
        // 提交任务前再次补建项目目录，避免项目创建时准备失败后无法恢复。
        projectService.prepareWorkspace(conversation.getProjectId(), ownerId);

        // 只查询是否存在活动任务；不再扫描全部历史并逐个请求 Python。
        if (agentTaskMapper.countActiveByConversationId(conversationId) > 0) {
            throw new BaseException(ErrorCode.CONVERSATION_STATE_CONFLICT);
        }

        // Java Task 表达用户可见的一轮对话；Python Run 表达实际的 Agent 执行。
        AgentTask task = new AgentTask();
        task.setId(UUID.randomUUID().toString());
        task.setConversationId(conversationId);
        task.setCreatedAt(OffsetDateTime.now(ZoneOffset.UTC));

        CreateRunRequest runRequest = new CreateRunRequest(conversation.getProjectId(), request.getPrompt());
        runRequest.setConversationId(conversationId);
        // 历史由 Python 根据 project_id、conversation_id 从 agent_run 读取。
        runRequest.setContext(List.of());

        RunStatusResponse run = pythonAgentClient.createRun(runRequest);
        if (run == null || run.getRunId() == null || run.getRunId().isBlank()) {
            throw new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR);
        }
        task.setPythonRunId(run.getRunId());
        task.setStatus(run.getStatus());

        try {
            int inserted = agentTaskMapper.insert(task);
            if (inserted != 1) {
                throw new IllegalStateException("agent_task insert returned " + inserted);
            }
        } catch (RuntimeException exception) {
            // Python 已经创建 Run 而 Java 保存失败；记录 run_id，明确报错，不自动重发。
            log.error("[任务保存失败] taskId: {}, conversationId: {}, runId: {}",
                    task.getId(), conversationId, run.getRunId(), exception);
            throw new BaseException(ErrorCode.AGENT_TASK_PERSIST_FAILED, exception);
        }
        return new CreateTurnResponse(task.getId(), conversationId, task.getPythonRunId(), task.getStatus());
    }

    @Override
    public TurnResponse getTurn(String conversationId, String taskId, String ownerId) {
        // prompt/status/result 来自 agent_run 关联查询，不依赖 SSE 是否送达。
        return toResponse(requireOwnedTask(conversationId, taskId, ownerId));
    }

    @Override
    public AgentTask requireOwnedTask(String conversationId, String taskId, String ownerId) {
        requireOwnedConversation(conversationId, ownerId);
        return agentTaskMapper.findById(taskId)
                .filter(task -> conversationId.equals(task.getConversationId()))
                .orElseThrow(() -> new BaseException(ErrorCode.AGENT_TASK_NOT_FOUND));
    }

    @Override
    public List<TurnResponse> listTurns(String conversationId, String ownerId) {
        requireOwnedConversation(conversationId, ownerId);
        return orderedTasks(conversationId).stream().map(this::toResponse).toList();
    }

    // 按对话 ID 查询并按创建时间排序，保持上下文轮次顺序稳定。
    private List<AgentTask> orderedTasks(String conversationId) {
        return agentTaskMapper.findByConversationId(conversationId);
    }

    /**
     * 对话读取沿 conversation -> project 链路检查归属。
     * 他人的项目统一映射成对话不存在，避免泄露资源是否存在。
     */
    private Conversation requireOwnedConversation(String conversationId, String ownerId) {
        Conversation conversation = conversationMapper.findById(conversationId)
                .orElseThrow(() -> new BaseException(ErrorCode.CONVERSATION_NOT_FOUND));
        try {
            projectService.requireOwnedProject(conversation.getProjectId(), ownerId);
        } catch (BaseException exception) {
            if (exception.getErrorCode() == ErrorCode.PROJECT_NOT_FOUND) {
                throw new BaseException(ErrorCode.CONVERSATION_NOT_FOUND);
            }
            throw exception;
        }
        return conversation;
    }

    // 内部实体与 HTTP 响应分开，避免把后续加入的内部字段直接暴露给前端。
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

    // 一个 AgentTask 对应用户可见的一轮对话；这里只负责字段映射。
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
