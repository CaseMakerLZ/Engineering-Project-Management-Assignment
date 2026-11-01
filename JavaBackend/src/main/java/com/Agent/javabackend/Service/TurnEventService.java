package com.Agent.javabackend.Service;

import com.Agent.javabackend.Client.PythonStreamClient;
import com.Agent.javabackend.Config.AgentStreamingConfig;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 把 Python 已有的 /runs/{run_id}/events 转发给浏览器。
 *
 * 认证和归属检查在 Controller 的请求线程中完成，本服务只接收明确的
 * session/task/conversation/run 标识。读取线程数量、连接数和单帧大小均有上限；
 * 清理只关闭本地连接，不取消 Python 中的 Agent 任务。
 */
@Slf4j
@Service
public class TurnEventService {
    private static final String LOCAL_SESSION = "local";
    private static final String STREAM_ERROR = "stream.error";

    private final PythonStreamClient pythonStreamClient;
    private final AgentStreamingConfig config;
    private final ObjectMapper objectMapper;
    private final Semaphore connectionPermits;
    private final ExecutorService readerExecutor;
    private final ConcurrentHashMap<String, Set<Connection>> connectionsBySession =
            new ConcurrentHashMap<>();
    private final AtomicInteger activeConnections = new AtomicInteger();

    public TurnEventService(PythonStreamClient pythonStreamClient,
                            AgentStreamingConfig config,
                            ObjectMapper objectMapper) {
        this.pythonStreamClient = pythonStreamClient;
        this.config = config;
        this.objectMapper = objectMapper;
        this.connectionPermits = new Semaphore(config.sseMaxConnections());
        ThreadFactory threadFactory = runnable -> {
            Thread thread = new Thread(runnable, "agent-sse-reader");
            thread.setDaemon(true);
            return thread;
        };
        this.readerExecutor = new ThreadPoolExecutor(
                config.sseMaxConnections(), config.sseMaxConnections(),
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(config.sseMaxConnections()),
                threadFactory,
                new ThreadPoolExecutor.AbortPolicy());
    }

    /**
     * 打开上游并返回浏览器 SSE 连接。
     *
     * 上游握手失败会抛出 BaseException，由全局异常处理返回普通 Result；
     * 此时浏览器响应还没有开始，不会出现半截 SSE。
     */
    public SseEmitter open(String sessionId, OffsetDateTime expiresAt,
                           String conversationId, String taskId, String runId) {
        String effectiveSession = sessionId == null || sessionId.isBlank()
                ? LOCAL_SESSION : sessionId;
        long timeoutMs = connectionTimeoutMillis(expiresAt);

        if (!connectionPermits.tryAcquire()) {
            throw new BaseException(ErrorCode.AGENT_STREAM_CONNECTION_LIMIT);
        }

        PythonStreamClient.UpstreamStream upstream;
        try {
            upstream = pythonStreamClient.openEvents(runId);
        } catch (RuntimeException exception) {
            connectionPermits.release();
            throw exception;
        }

        SseEmitter emitter;
        Connection connection;
        try {
            emitter = new SseEmitter(timeoutMs);
            connection = new Connection(
                    effectiveSession, conversationId, taskId, runId, upstream, emitter);
        } catch (RuntimeException exception) {
            upstream.close();
            connectionPermits.release();
            throw exception;
        }
        boolean registered = false;
        try {
            register(connection);
            registered = true;
            emitter.onCompletion(() -> cleanup(connection, false));
            emitter.onTimeout(() -> cleanup(connection, false));
            emitter.onError(error -> cleanup(connection, false));
            readerExecutor.execute(() -> readLoop(connection));
            return emitter;
        } catch (RuntimeException exception) {
            if (registered) {
                cleanup(connection, false);
            } else {
                upstream.close();
                connectionPermits.release();
            }
            if (exception instanceof RejectedExecutionException) {
                throw new BaseException(ErrorCode.AGENT_STREAM_CONNECTION_LIMIT);
            }
            throw exception;
        }
    }

    /** 退出登录时关闭这个 session 的所有 SSE；不停止 Agent。 */
    public void closeSession(String sessionId) {
        if (sessionId == null) {
            return;
        }
        Set<Connection> connections = connectionsBySession.get(sessionId);
        if (connections == null) {
            return;
        }
        for (Connection connection : List.copyOf(connections)) {
            cleanup(connection, true);
        }
    }

    int activeConnections() {
        return activeConnections.get();
    }

    private void readLoop(Connection connection) {
        SseFrameParser parser = new SseFrameParser(config.sseMaxFrameBytes());
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                connection.upstream.body(), StandardCharsets.UTF_8))) {
            String line;
            while (!connection.closed.get()
                    && (line = readLineLimited(reader, config.sseMaxFrameBytes())) != null) {
                SseFrameParser.Frame frame = parser.acceptLine(line);
                if (frame != null) {
                    forward(connection, frame);
                }
            }
            if (!connection.closed.get()) {
                SseFrameParser.Frame last = parser.finish();
                if (last != null) {
                    forward(connection, last);
                }
            }
        } catch (SseFrameParser.FrameTooLargeException exception) {
            sendStreamError(connection, "FRAME_LIMIT_EXCEEDED",
                    "实时事件超过大小限制", false);
        } catch (IOException exception) {
            if (!connection.closed.get()) {
                sendStreamError(connection, "STREAM_INTERRUPTED",
                        "实时连接中断，请重新连接", true);
            }
        } catch (RuntimeException exception) {
            log.warn("[实时事件转发异常] taskId: {}, runId: {}, 原因: {}",
                    connection.taskId, connection.runId, exception.getClass().getSimpleName());
            if (!connection.closed.get()) {
                sendStreamError(connection, "STREAM_PROTOCOL_ERROR",
                        "实时事件格式异常，请重新连接", false);
            }
        } finally {
            cleanup(connection, true);
        }
    }

    /**
     * 单行也设置上限，避免上游在缺少换行时让 BufferedReader.readLine
     * 无限增长。按字符数限制内存，帧的 UTF-8 字节上限仍由 SseFrameParser 检查。
     */
    private String readLineLimited(BufferedReader reader, int maxChars) throws IOException {
        StringBuilder line = new StringBuilder();
        int value;
        while ((value = reader.read()) != -1) {
            if (value == '\n') {
                return line.toString();
            }
            if (value == '\r') {
                reader.mark(1);
                int next = reader.read();
                if (next != '\n' && next != -1) {
                    reader.reset();
                }
                return line.toString();
            }
            if (line.length() >= maxChars) {
                throw new SseFrameParser.FrameTooLargeException();
            }
            line.append((char) value);
        }
        return line.isEmpty() ? null : line.toString();
    }

    private void forward(Connection connection, SseFrameParser.Frame frame) throws IOException {
        if (frame.isCommentOnly()) {
            // 心跳只是“连接还在”，不能当成助手消息或普通 JSON 事件。
            connection.emitter.send(SseEmitter.event()
                    .comment(String.join(" ", frame.comments())));
            return;
        }
        if (!frame.hasData()) {
            return;
        }

        JsonNode parsed = objectMapper.readTree(frame.data());
        if (!parsed.isObject()) {
            throw new IllegalArgumentException("SSE data 不是 JSON 对象");
        }
        ObjectNode data = (ObjectNode) parsed;
        // Python 已有 run_id/sequence/created_at；Java 只补两个业务标识，不改序号。
        data.put("task_id", connection.taskId);
        data.put("conversation_id", connection.conversationId);
        JsonNode sequence = data.get("sequence");
        if (sequence != null && sequence.isNumber()) {
            connection.lastSequence = sequence.asInt();
        }

        SseEmitter.SseEventBuilder builder = SseEmitter.event();
        if (frame.event() != null && !frame.event().isBlank()) {
            builder.name(frame.event());
        }
        if (frame.id() != null && !frame.id().isBlank()) {
            builder.id(frame.id());
        }
        builder.data(objectMapper.writeValueAsString(data));
        connection.emitter.send(builder);
    }

    private void sendStreamError(Connection connection, String code,
                                 String message, boolean retryable) {
        ObjectNode payload = objectMapper.createObjectNode();
        payload.put("task_id", connection.taskId);
        payload.put("conversation_id", connection.conversationId);
        payload.put("run_id", connection.runId);
        payload.put("sequence", connection.lastSequence);
        payload.put("created_at", OffsetDateTime.now(ZoneOffset.UTC).toString());
        payload.put("code", code);
        payload.put("message", message);
        payload.put("retryable", retryable);
        try {
            connection.emitter.send(SseEmitter.event()
                    .name(STREAM_ERROR)
                    .id(Integer.toString(connection.lastSequence))
                    .data(objectMapper.writeValueAsString(payload)));
        } catch (IOException | RuntimeException ignored) {
            // 浏览器已断开时没有可写的通道，清理函数仍会释放上游和连接名额。
        }
    }

    private long connectionTimeoutMillis(OffsetDateTime expiresAt) {
        long configured = config.sseConnectionTimeoutMs();
        if (expiresAt == null) {
            return configured;
        }
        long remaining = Duration.between(OffsetDateTime.now(ZoneOffset.UTC), expiresAt).toMillis();
        if (remaining <= 0) {
            throw new BaseException(ErrorCode.AUTH_TOKEN_INVALID);
        }
        return Math.min(configured, remaining);
    }

    private void register(Connection connection) {
        connectionsBySession
                .computeIfAbsent(connection.sessionId, ignored -> ConcurrentHashMap.newKeySet())
                .add(connection);
        activeConnections.incrementAndGet();
    }

    private void cleanup(Connection connection, boolean completeEmitter) {
        if (!connection.closed.compareAndSet(false, true)) {
            return;
        }

        Set<Connection> connections = connectionsBySession.get(connection.sessionId);
        if (connections != null) {
            connections.remove(connection);
            if (connections.isEmpty()) {
                connectionsBySession.remove(connection.sessionId, connections);
            }
        }
        activeConnections.decrementAndGet();

        try {
            connection.upstream.close();
        } finally {
            if (completeEmitter) {
                try {
                    connection.emitter.complete();
                } catch (RuntimeException ignored) {
                    // 容器已经结束该连接。
                }
            }
            connectionPermits.release();
        }
    }

    @PreDestroy
    public void shutdown() {
        for (Set<Connection> connections : List.copyOf(connectionsBySession.values())) {
            for (Connection connection : List.copyOf(connections)) {
                cleanup(connection, true);
            }
        }
        readerExecutor.shutdownNow();
    }

    private static final class Connection {
        private final String sessionId;
        private final String conversationId;
        private final String taskId;
        private final String runId;
        private final PythonStreamClient.UpstreamStream upstream;
        private final SseEmitter emitter;
        private final AtomicBoolean closed = new AtomicBoolean(false);
        private volatile int lastSequence;

        private Connection(String sessionId, String conversationId, String taskId,
                           String runId, PythonStreamClient.UpstreamStream upstream,
                           SseEmitter emitter) {
            this.sessionId = sessionId;
            this.conversationId = conversationId;
            this.taskId = taskId;
            this.runId = runId;
            this.upstream = upstream;
            this.emitter = emitter;
        }
    }
}
