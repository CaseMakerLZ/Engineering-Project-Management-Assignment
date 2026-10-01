package com.Agent.javabackend.Service;

import com.Agent.javabackend.Client.PythonAgentClient;
import com.Agent.javabackend.Service.impl.ConversationServiceImpl;
import com.Agent.javabackend.Service.impl.ProjectServiceImpl;
import com.Agent.javabackend.dto.CreateRunRequest;
import com.Agent.javabackend.dto.CreateRunResponse;
import com.Agent.javabackend.dto.RunResponse;
import com.Agent.javabackend.dto.RunStatus;
import com.Agent.javabackend.dto.ConversationDTO.CreateConversationRequest;
import com.Agent.javabackend.dto.ConversationDTO.CreateTurnRequest;
import com.Agent.javabackend.dto.ProjectDTO.CreateProjectRequest;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class ConversationServiceImplTest {
    @Test
    void secondTurnReceivesFirstAnswerAndRejectsParallelTurn() {
        PythonAgentClient client = mock(PythonAgentClient.class);
        ProjectServiceImpl projects = new ProjectServiceImpl();
        ConversationServiceImpl conversations = new ConversationServiceImpl(projects, client);
        CreateProjectRequest projectRequest = new CreateProjectRequest();
        projectRequest.setName("Study project");
        String projectId = projects.create(projectRequest).getProjectId();
        String conversationId = conversations.create(projectId, new CreateConversationRequest("Design"))
                .getConversationId();

        when(client.createRun(any(CreateRunRequest.class)))
                .thenReturn(new CreateRunResponse("run-1", RunStatus.CREATED))
                .thenReturn(new CreateRunResponse("run-2", RunStatus.CREATED));
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
        assertEquals(2, secondRun.getContext().size());
        assertEquals("first question", secondRun.getContext().get(0).content());
        assertEquals("first answer", secondRun.getContext().get(1).content());
    }
}
