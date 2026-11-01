package com.Agent.javabackend.Client;

import com.Agent.javabackend.dto.CreateRunRequest;
import com.Agent.javabackend.dto.ProjectFileDTO.ProjectFileContentResponse;
import com.Agent.javabackend.dto.ProjectFileDTO.ProjectFileTreeResponse;
import com.Agent.javabackend.dto.ProjectDTO.ProjectWorkspaceResponse;
import com.Agent.javabackend.dto.RunResponse;
import com.Agent.javabackend.dto.RunStatusResponse;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.ObjectMapper;

import java.net.SocketTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.List;
import java.util.Optional;
import java.util.function.Supplier;

/**
 * Python Agent Service 的 HTTP 通信适配器。
 *
 * 这个类只负责远程调用细节：接口路径、HTTP 方法、请求体和响应 DTO。
 * Java 业务服务不需要直接依赖 RestClient，也不需要知道 Python 的 URL 结构。
 */
@Component
public class PythonAgentClient {
    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public PythonAgentClient(RestClient restClient) {
        this(restClient, new ObjectMapper());
    }

    @Autowired
    public PythonAgentClient(RestClient restClient, ObjectMapper objectMapper) {
        this.restClient = restClient;
        this.objectMapper = objectMapper;
    }

    public RunResponse getRun(String runId) {
        return execute(() -> restClient.get()
                .uri("/api/internal/runs/{runId}", runId)
                .retrieve()
                .body(RunResponse.class));
    }

    public RunStatusResponse createRun(CreateRunRequest request) {
        return execute(() -> restClient.post()
                .uri("/api/internal/runs")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(RunStatusResponse.class));
    }

    /**
     * 让 Python 根据已提交的项目记录准备真实工作区。
     * 调用方必须保证项目已经落库；重复调用由 Python 保证幂等。
     */
    public void prepareWorkspace(String projectId) {
        ProjectWorkspaceResponse response = execute(() -> restClient.put()
                .uri("/api/internal/projects/{projectId}/workspace", projectId)
                .retrieve()
                .body(ProjectWorkspaceResponse.class));
        if (response == null
                || !Boolean.TRUE.equals(response.getReady())
                || !projectId.equals(response.getProjectId())) {
            throw new BaseException(
                    ErrorCode.AGENT_SERVICE_RESPONSE_ERROR,
                    "Python 返回的项目工作区状态无效");
        }
    }

    /**
     * 读取项目内某个目录的直接子项。
     * 分页游标由 Python 创建并绑定项目和目录，Java 只做参数透传。
     */
    public ProjectFileTreeResponse getFileTree(
            String projectId, String path, int pageSize, String cursor) {
        ProjectFileTreeResponse response = executeFile(() -> restClient.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/api/internal/projects/{projectId}/files/tree")
                        .queryParam("path", path)
                        .queryParam("page_size", pageSize)
                        .queryParamIfPresent("cursor", Optional.ofNullable(cursor)
                                .filter(value -> !value.isBlank()))
                        .build(projectId))
                .retrieve()
                .body(ProjectFileTreeResponse.class), PythonErrorTranslator.Kind.FILE);
        if (response == null || !projectId.equals(response.getProjectId())) {
            throw new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR);
        }
        if (response.getEntries() == null) {
            response.setEntries(List.of());
        }
        return response;
    }

    /** 读取一个允许预览的 UTF-8 文本文件；二进制、编码或大小限制由 Python 拒绝。 */
    public ProjectFileContentResponse getFileContent(String projectId, String path) {
        ProjectFileContentResponse response = executeFile(() -> restClient.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/api/internal/projects/{projectId}/files/content")
                        .queryParam("path", path)
                        .build(projectId))
                .retrieve()
                .body(ProjectFileContentResponse.class), PythonErrorTranslator.Kind.FILE);
        if (response == null || !projectId.equals(response.getProjectId())) {
            throw new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR);
        }
        return response;
    }

    private <T> T execute(Supplier<T> request) {
        return execute(request, PythonErrorTranslator.Kind.RUN);
    }

    private <T> T executeFile(Supplier<T> request, PythonErrorTranslator.Kind kind) {
        return execute(request, kind);
    }

    private <T> T execute(Supplier<T> request, PythonErrorTranslator.Kind kind) {
        try {
            return request.get();
        } catch (HttpStatusCodeException ex) {
            throw PythonErrorTranslator.translate(
                    ex.getStatusCode().value(), ex.getResponseBodyAsString(), objectMapper, kind);
        } catch (ResourceAccessException ex) {
            if (isTimeout(ex)) {
                throw new BaseException(ErrorCode.AGENT_SERVICE_TIMEOUT, ex);
            }
            throw new BaseException(ErrorCode.AGENT_SERVICE_UNAVAILABLE, ex);
        } catch (RestClientException ex) {
            throw new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR, ex);
        }
    }

    private boolean isTimeout(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            if (current instanceof SocketTimeoutException || current instanceof HttpTimeoutException) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
