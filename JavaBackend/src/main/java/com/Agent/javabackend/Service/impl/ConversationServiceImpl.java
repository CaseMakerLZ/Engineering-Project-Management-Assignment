package com.Agent.javabackend.Service.impl;

import com.Agent.javabackend.Client.PythonAgentClient;
import com.Agent.javabackend.Mapper.AgentTaskMapper;
import com.Agent.javabackend.Mapper.ConversationMapper;
import com.Agent.javabackend.Service.ContextService;
import com.Agent.javabackend.Service.ConversationService;
import com.Agent.javabackend.Service.ProjectService;
import com.Agent.javabackend.dto.CreateRunRequest;
import com.Agent.javabackend.dto.RunResponse;
import com.Agent.javabackend.dto.RunStatus;
import com.Agent.javabackend.dto.RunStatusResponse;
import com.Agent.javabackend.dto.ConversationDTO.*;
import com.Agent.javabackend.entity.MessageContainer.AgentTask;
import com.Agent.javabackend.entity.MessageContainer.Conversation;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Service
public class ConversationServiceImpl implements ConversationService {
    private final ProjectService projectService;
    private final PythonAgentClient pythonAgentClient;
    private final ConversationMapper conversationMapper;
    private final AgentTaskMapper agentTaskMapper;
    private final ContextService contextService;

    public ConversationServiceImpl(ProjectService projectService, PythonAgentClient pythonAgentClient,
                                   ConversationMapper conversations, AgentTaskMapper tasks, ContextService contextService) {
        this.projectService = projectService;
        this.pythonAgentClient = pythonAgentClient;
        this.conversationMapper = conversations;
        this.agentTaskMapper = tasks;
        this.contextService = contextService;
    }

    @Override
    public ConversationResponse create(String projectId, CreateConversationRequest request) {
        // 对话必须归属于一个已经存在的项目。
        projectService.requireExists(projectId);
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
    public ConversationResponse get(String conversationId) {
        return toResponse(requireConversation(conversationId));
    }

    @Override
    public List<ConversationResponse> list(String projectId) {
        projectService.requireExists(projectId);
        return conversationMapper.findByProjectId(projectId).stream()
                .map(this::toResponse).toList();
    }
/** ==================================此线以上为conversation相关，此线以下(除了private方法)全与Turn有关========================================================*/
    @Override
    public synchronized CreateTurnResponse createTurn(String conversationId, CreateTurnRequest request) {
        Conversation conversation = requireConversation(conversationId);

        // Java 只记录上一次查询到的状态；提交新一轮之前先向 Python 同步。
        // 同一段对话有未完成任务时，不能继续提交，否则两轮会读到相同的历史。
        List<AgentTask> previous = orderedTasks(conversationId);
        for (AgentTask task : previous) {
            refreshFromPython(task);
            if (task.getStatus() == RunStatus.CREATED || task.getStatus() == RunStatus.RUNNING) {
                throw new BaseException(ErrorCode.CONVERSATION_STATE_CONFLICT);
            }
        }

        //组装上下文
        List<ContextMessage> context = contextService.assembleContext(previous);

        // Java Task 表达用户可见的一轮对话；Python Run 表达实际的 Agent 执行。
        AgentTask task = new AgentTask();
        task.setId(UUID.randomUUID().toString());
        task.setConversationId(conversationId);
        task.setPrompt(request.getPrompt());
        task.setStatus(RunStatus.CREATED);
        task.setCreatedAt(OffsetDateTime.now(ZoneOffset.UTC));

        CreateRunRequest runRequest = new CreateRunRequest(conversation.getProjectId(), request.getPrompt());
        runRequest.setConversationId(conversationId);
        runRequest.setContext(context);
        // Python 创建任务成功后再保存 Java Task，避免生成没有 run_id 的孤立任务。
        RunStatusResponse run = pythonAgentClient.createRun(runRequest);
        task.setPythonRunId(run.getRunId());
        task.setStatus(run.getStatus());
        agentTaskMapper.insert(task);
        return new CreateTurnResponse(task.getId(), conversationId, task.getPythonRunId(), task.getStatus());
    }

    @Override
    public TurnResponse getTurn(String conversationId, String taskId) {
        requireConversationExists(conversationId);
        AgentTask task = agentTaskMapper.findById(taskId).orElse(null);
        if (task == null || !conversationId.equals(task.getConversationId())) {
            throw new BaseException(ErrorCode.AGENT_TASK_NOT_FOUND);
        }
        refreshFromPython(task);
        return toResponse(task);
    }

    @Override
    public List<TurnResponse> listTurns(String conversationId) {
        requireConversationExists(conversationId);
        List<AgentTask> ordered = orderedTasks(conversationId);
        ordered.forEach(this::refreshFromPython);
        return ordered.stream().map(this::toResponse).toList();
    }

    /**
     * Java 的任务状态是一次快照；仅在尚未结束时查询 Python 的最新执行结果。
     * 已结束的任务保留本地结果，避免每次读取历史都调用 Python。
     */
    private void refreshFromPython(AgentTask task) {
        if (task.getStatus() != RunStatus.CREATED && task.getStatus() != RunStatus.RUNNING) {
            return;
        }
        RunResponse run = pythonAgentClient.getRun(task.getPythonRunId());
        task.setStatus(run.getStatus());
        task.setResult(run.getResult());
        task.setError(run.getError());
        task.setStartedAt(run.getStartedAt());
        task.setFinishedAt(run.getFinishedAt());
        agentTaskMapper.updateExecution(task);
    }

    // 按对话 ID 查询并按创建时间排序，保持上下文轮次顺序稳定。
    private List<AgentTask> orderedTasks(String conversationId) {
        return agentTaskMapper.findByConversationId(conversationId);
    }

    /** 只检查存在性，适用于不需要使用 Conversation 对象的查询方法。 */
    private void requireConversationExists(String conversationId) {
        if (conversationMapper.findById(conversationId).isEmpty()) {
            throw new BaseException(ErrorCode.CONVERSATION_NOT_FOUND);
        }
    }

    //查找指定conversationId的对话，不存在则抛异常
    private Conversation requireConversation(String conversationId) {
        return conversationMapper.findById(conversationId)
                .orElseThrow(() -> new BaseException(ErrorCode.CONVERSATION_NOT_FOUND));
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
