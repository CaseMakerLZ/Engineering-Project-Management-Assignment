package com.Agent.javabackend.Client;

import com.Agent.javabackend.dto.CreateRunRequest;
import com.Agent.javabackend.dto.RunResponse;
import com.Agent.javabackend.dto.RunStatusResponse;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClient;

import java.net.SocketTimeoutException;
import java.net.http.HttpTimeoutException;
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

    public PythonAgentClient(RestClient restClient) {
        this.restClient = restClient;
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

    private <T> T execute(Supplier<T> request) {
        try {
            return request.get();
        } catch (HttpStatusCodeException ex) {
            throw translateStatusException(ex);
        } catch (ResourceAccessException ex) {
            if (isTimeout(ex)) {
                throw new BaseException(ErrorCode.AGENT_SERVICE_TIMEOUT, ex);
            }
            throw new BaseException(ErrorCode.AGENT_SERVICE_UNAVAILABLE, ex);
        } catch (RestClientException ex) {
            throw new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR, ex);
        }
    }

    private BaseException translateStatusException(HttpStatusCodeException ex) {
        int status = ex.getStatusCode().value();
        if (status == 404) {
            return new BaseException(ErrorCode.AGENT_RUN_NOT_FOUND, ex);
        }
        if (status == 409) {
            return new BaseException(ErrorCode.AGENT_RUN_STATE_CONFLICT, ex);
        }
        if (status == 422) {
            return new BaseException(ErrorCode.INVALID_ARGUMENT, ex);
        }
        if (status == 401 || status == 403) {
            return new BaseException(ErrorCode.AGENT_SERVICE_AUTH_FAILED, ex);
        }
        if (status == 408 || status == 504) {
            return new BaseException(ErrorCode.AGENT_SERVICE_TIMEOUT, ex);
        }
        if (status == 503) {
            return new BaseException(ErrorCode.AGENT_SERVICE_UNAVAILABLE, ex);
        }
        return new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR, ex);
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
