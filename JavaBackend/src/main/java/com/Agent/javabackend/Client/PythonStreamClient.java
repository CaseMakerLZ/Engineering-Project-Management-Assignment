package com.Agent.javabackend.Client;

import com.Agent.javabackend.Config.AgentStreamingConfig;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;
import tools.jackson.databind.ObjectMapper;

import java.io.Closeable;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.URI;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Python 长连接的 HTTP 适配器。
 *
 * SSE 和大文件下载不能先收完整段响应再返回，因此这里直接管理
 * HttpURLConnection，并保留输入流供上层边读边转发。连接数上限由
 * TurnEventService 控制，本类只负责打开、校验和关闭。
 */
@Component
public class PythonStreamClient {
    private static final int MAX_ERROR_BODY_BYTES = 8192;

    private final AgentStreamingConfig config;
    private final ObjectMapper objectMapper;

    public PythonStreamClient(AgentStreamingConfig config, ObjectMapper objectMapper) {
        this.config = config;
        this.objectMapper = objectMapper;
    }

    /** 先完成上游握手并检查 text/event-stream，再把输入流交给转发服务。 */
    public UpstreamStream openEvents(String runId) {
        URI uri = UriComponentsBuilder.fromUriString(config.baseUrl())
                .pathSegment("api", "internal", "runs", runId, "events")
                .build()
                .toUri();
        return open(uri, "text/event-stream", PythonErrorTranslator.Kind.STREAM,
                config.sseConnectTimeoutMs(), config.sseIdleTimeoutMs(), true);
    }

    public UpstreamStream openDownload(String projectId, String path) {
        URI uri = UriComponentsBuilder.fromUriString(config.baseUrl())
                .pathSegment("api", "internal", "projects", projectId, "files", "download")
                .queryParam("path", path)
                .build()
                .encode()
                .toUri();
        return open(uri, "application/octet-stream", PythonErrorTranslator.Kind.FILE,
                config.fileConnectTimeoutMs(), config.fileReadTimeoutMs(), false);
    }

    public UpstreamStream openArchive(String projectId) {
        URI uri = UriComponentsBuilder.fromUriString(config.baseUrl())
                .pathSegment("api", "internal", "projects", projectId, "archive")
                .build()
                .toUri();
        return open(uri, "application/zip", PythonErrorTranslator.Kind.ARCHIVE,
                config.fileConnectTimeoutMs(), config.fileReadTimeoutMs(), false);
    }

    private UpstreamStream open(URI uri, String accept, PythonErrorTranslator.Kind kind,
                                long connectTimeoutMs, long readTimeoutMs, boolean requireEventStream) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) uri.toURL().openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(Math.toIntExact(connectTimeoutMs));
            connection.setReadTimeout(Math.toIntExact(readTimeoutMs));
            connection.setUseCaches(false);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty(HttpHeaders.ACCEPT, accept);
            connection.setRequestProperty(HttpHeaders.CACHE_CONTROL, "no-cache");
            if (!config.token().isBlank()) {
                connection.setRequestProperty("X-Service-Token", config.token());
            }

            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                String errorBody = readLimited(connection.getErrorStream());
                connection.disconnect();
                throw PythonErrorTranslator.translate(status, errorBody, objectMapper, kind);
            }

            String contentType = connection.getContentType();
            if (requireEventStream && !isEventStream(contentType)) {
                connection.disconnect();
                throw new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR);
            }

            InputStream body = connection.getInputStream();
            return new UpstreamStream(
                    body, connection.getContentLengthLong(), contentType, connection::disconnect);
        } catch (BaseException exception) {
            if (connection != null) {
                connection.disconnect();
            }
            throw exception;
        } catch (IOException exception) {
            if (connection != null) {
                connection.disconnect();
            }
            if (isTimeout(exception)) {
                throw new BaseException(ErrorCode.AGENT_SERVICE_TIMEOUT, exception);
            }
            throw new BaseException(ErrorCode.AGENT_SERVICE_UNAVAILABLE, exception);
        }
    }

    private String readLimited(InputStream stream) {
        if (stream == null) {
            return "";
        }
        try (InputStream input = stream) {
            return new String(input.readNBytes(MAX_ERROR_BODY_BYTES), StandardCharsets.UTF_8);
        } catch (IOException ignored) {
            return "";
        }
    }

    private boolean isEventStream(String contentType) {
        if (contentType == null) {
            return false;
        }
        int semicolon = contentType.indexOf(';');
        String mediaType = semicolon >= 0 ? contentType.substring(0, semicolon) : contentType;
        return "text/event-stream".equalsIgnoreCase(mediaType.trim());
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

    /** 一条已经完成握手、可以边读边转发的上游响应。 */
    public static final class UpstreamStream implements Closeable {
        private final InputStream body;
        private final long contentLength;
        private final String contentType;
        private final Runnable closeAction;
        private final AtomicBoolean closed = new AtomicBoolean(false);

        public UpstreamStream(InputStream body, long contentLength, String contentType, Runnable closeAction) {
            this.body = body;
            this.contentLength = contentLength;
            this.contentType = contentType;
            this.closeAction = closeAction;
        }

        public InputStream body() {
            return body;
        }

        public long contentLength() {
            return contentLength;
        }

        public String contentType() {
            return contentType;
        }

        @Override
        public void close() {
            if (!closed.compareAndSet(false, true)) {
                return;
            }
            try {
                body.close();
            } catch (IOException ignored) {
                // 关闭上游失败不影响本地清理登记。
            } finally {
                closeAction.run();
            }
        }
    }
}
