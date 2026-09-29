package com.Agent.javabackend.Controller;

import com.Agent.javabackend.Service.AgentService;
import com.Agent.javabackend.dto.CreateRunResponse;
import com.Agent.javabackend.dto.RunStatus;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import com.Agent.javabackend.exception.GlobalExceptionHandler;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.UUID;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class AgentServiceControllerTest {
    private AgentService agentService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        agentService = mock(AgentService.class);
        mockMvc = standaloneSetup(new AgentServiceController(agentService))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    void baseExceptionReturnsItsHttpStatusAndBusinessCode() throws Exception {
        when(agentService.health()).thenThrow(
                new BaseException(ErrorCode.AGENT_SERVICE_UNAVAILABLE)
        );

        mockMvc.perform(get("/api/agent/health"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value(40001))
                .andExpect(jsonPath("$.msg").value("Agent服务暂不可用"));
    }

    @Test
    void timeoutExceptionReturns504AndBusinessCode40002() throws Exception {
        when(agentService.health()).thenThrow(
                new BaseException(ErrorCode.AGENT_SERVICE_TIMEOUT)
        );

        mockMvc.perform(get("/api/agent/health"))
                .andExpect(status().isGatewayTimeout())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value(40002))
                .andExpect(jsonPath("$.msg").value("Agent 服务调用超时"));
    }

    @Test
    void invalidPromptReturns400AndBusinessCode10001() throws Exception {
        mockMvc.perform(post("/api/agent/runs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"project_id\":\"p1\",\"prompt\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value(10001))
                .andExpect(jsonPath("$.msg").value("prompt不得为空"));
    }

    @Test
    void malformedJsonReturnsUnified400Response() throws Exception {
        mockMvc.perform(post("/api/agent/runs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{not-json}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void createRunReturns202JsonAndDoesNotReflectMaliciousPrompt() throws Exception {
        String runId = UUID.randomUUID().toString();
        when(agentService.createRun(any())).thenReturn(
                new CreateRunResponse(runId, RunStatus.CREATED)
        );

        mockMvc.perform(post("/api/agent/runs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"project_id\":\"p1\",\"prompt\":\"<script>alert(1)</script>\"}"))
                .andExpect(status().isAccepted())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.run_id").value(runId))
                .andExpect(content().string(not(containsString("<script>"))));
    }

    @Test
    void unknownExceptionReturns500AndGenericBusinessCode() throws Exception {
        when(agentService.health()).thenThrow(new IllegalStateException("secret detail"));

        mockMvc.perform(get("/api/agent/health"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value(90001))
                .andExpect(jsonPath("$.msg").value("系统内部错误"));
    }
}
