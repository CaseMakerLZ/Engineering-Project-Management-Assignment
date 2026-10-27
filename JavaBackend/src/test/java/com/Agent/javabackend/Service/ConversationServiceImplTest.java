package com.Agent.javabackend.Service;

import com.Agent.javabackend.Client.PythonAgentClient;
import com.Agent.javabackend.Service.impl.ConversationServiceImpl;
import com.Agent.javabackend.Service.impl.ProjectServiceImpl;
import com.Agent.javabackend.Mapper.ProjectMapper;
import com.Agent.javabackend.Mapper.ConversationMapper;
import com.Agent.javabackend.Mapper.AgentTaskMapper;
import com.Agent.javabackend.dto.CreateRunRequest;
import com.Agent.javabackend.dto.RunStatusResponse;
import com.Agent.javabackend.dto.RunResponse;
import com.Agent.javabackend.dto.RunStatus;
import com.Agent.javabackend.dto.ConversationDTO.CreateConversationRequest;
import com.Agent.javabackend.dto.ConversationDTO.CreateTurnRequest;
import com.Agent.javabackend.dto.ProjectDTO.CreateProjectRequest;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class ConversationServiceImplTest {
    /** 验证同一对话不能并行提交，且 Java 不再给第二轮请求附加历史上下文。 */
    @Test
    void secondTurnSendsNoJavaContextAndRejectsParallelTurn() {
        PythonAgentClient client = mock(PythonAgentClient.class);
        ProjectMapper projectRepository = mock(ProjectMapper.class);
        ConversationMapper conversationRepository = mock(ConversationMapper.class);
        AgentTaskMapper taskRepository = mock(AgentTaskMapper.class);
        ProjectServiceImpl projects = new ProjectServiceImpl(projectRepository, "local");
        ConversationServiceImpl conversations = new ConversationServiceImpl(projects, client,
                conversationRepository, taskRepository);
        CreateProjectRequest projectRequest = new CreateProjectRequest();
        projectRequest.setName("Study project");
        projectRequest.setLocalPath(Paths.get(".").toAbsolutePath().toString());
        String projectId = projects.create(projectRequest).getProjectId();
        var projectCaptor = org.mockito.ArgumentCaptor.forClass(com.Agent.javabackend.entity.MessageContainer.Project.class);
        verify(projectRepository).insert(projectCaptor.capture());
        when(projectRepository.findById(projectId)).thenReturn(Optional.of(projectCaptor.getValue()));
        var conversationCaptor = org.mockito.ArgumentCaptor.forClass(com.Agent.javabackend.entity.MessageContainer.Conversation.class);
        String conversationId = conversations.create(projectId, new CreateConversationRequest("Design"))
                .getConversationId();
        verify(conversationRepository).insert(conversationCaptor.capture());
        when(conversationRepository.findById(conversationId)).thenReturn(Optional.of(conversationCaptor.getValue()));

        List<com.Agent.javabackend.entity.MessageContainer.AgentTask> savedTasks = new ArrayList<>();
        doAnswer(invocation -> { savedTasks.add(invocation.getArgument(0)); return null; })
                .when(taskRepository).insert(any());
        when(taskRepository.findByConversationId(conversationId)).thenAnswer(invocation -> List.copyOf(savedTasks));

        when(client.createRun(any(CreateRunRequest.class)))
                .thenReturn(new RunStatusResponse("run-1", RunStatus.CREATED))
                .thenReturn(new RunStatusResponse("run-2", RunStatus.CREATED));
        CreateTurnRequest first = new CreateTurnRequest();
        first.setPrompt("first question");
        conversations.createTurn(conversationId, first);

        RunResponse running = new RunResponse();
        running.setStatus(RunStatus.RUNNING);
        when(client.getRun("run-1")).thenReturn(running);
        BaseException conflict = assertThrows(BaseException.class,
                () -> conversations.createTurn(conversationId, first));
        assertEquals(ErrorCode.CONVERSATION_STATE_CONFLICT, conflict.getErrorCode());

        RunResponse completed = new RunResponse();
        completed.setStatus(RunStatus.COMPLETED);
        completed.setResult("first answer");
        when(client.getRun("run-1")).thenReturn(completed);
        CreateTurnRequest second = new CreateTurnRequest();
        second.setPrompt("follow up");
        conversations.createTurn(conversationId, second);

        var requestCaptor = org.mockito.ArgumentCaptor.forClass(CreateRunRequest.class);
        verify(client, times(2)).createRun(requestCaptor.capture());
        CreateRunRequest secondRun = requestCaptor.getAllValues().get(1);
        assertEquals(conversationId, secondRun.getConversationId());
        // Java 只提交当前问题和对话身份；历史由 Python 从 agent_run 读取。
        assertEquals(List.of(), secondRun.getContext());
    }
}
