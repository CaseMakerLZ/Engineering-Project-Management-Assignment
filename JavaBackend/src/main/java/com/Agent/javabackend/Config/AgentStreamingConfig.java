package com.Agent.javabackend.Config;

/**
 * 实时事件和文件流使用独立于普通短请求的超时与容量配置。
 *
 * 普通 RestClient 仍保留 30 秒总读取等待；这里的长连接按空闲时间计算，
 * 避免一条正常运行的 SSE 或大文件下载被普通请求超时提前打断。
 */
public record AgentStreamingConfig(
        String baseUrl,
        String token,
        long sseConnectTimeoutMs,
        long sseIdleTimeoutMs,
        long sseConnectionTimeoutMs,
        int sseMaxConnections,
        int sseMaxFrameBytes,
        long fileConnectTimeoutMs,
        long fileReadTimeoutMs) {

    public AgentStreamingConfig {
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new IllegalArgumentException("agent-service.base-url 不得为空");
        }
        baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        token = token == null ? "" : token;
        if (sseConnectTimeoutMs <= 0 || sseIdleTimeoutMs <= 0 || sseConnectionTimeoutMs <= 0
                || fileConnectTimeoutMs <= 0 || fileReadTimeoutMs <= 0) {
            throw new IllegalArgumentException("流式连接超时必须大于零");
        }
        if (sseMaxConnections < 1 || sseMaxConnections > 512) {
            throw new IllegalArgumentException("agent-service.sse.max-connections 必须在 1 到 512 之间");
        }
        if (sseMaxFrameBytes < 1024) {
            throw new IllegalArgumentException("agent-service.sse.max-frame-bytes 不得小于 1024");
        }
    }
}
