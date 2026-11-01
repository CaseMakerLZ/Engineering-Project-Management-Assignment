package com.Agent.javabackend.Service;

import com.Agent.javabackend.Client.PythonAgentClient;
import com.Agent.javabackend.Client.PythonStreamClient;
import com.Agent.javabackend.dto.ProjectFileDTO.ProjectFileContentResponse;
import com.Agent.javabackend.dto.ProjectFileDTO.ProjectFileTreeResponse;
import com.Agent.javabackend.entity.MessageContainer.Project;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

/**
 * 云端项目文件接口的业务层。
 *
 * Java 负责用户、项目归属和参数边界；真实路径、文件类型、敏感文件、
 * 大小和分页游标由 Python 文件服务检查，Java 不自行猜测真实路径。
 */
@Slf4j
@Service
public class ProjectFileService {
    private static final int MAX_PAGE_SIZE = 200;
    private static final int MAX_PATH_LENGTH = 1024;
    private static final int MAX_CURSOR_LENGTH = 4096;
    private static final int COPY_BUFFER_BYTES = 8192;

    private final ProjectService projectService;
    private final PythonAgentClient pythonAgentClient;
    private final PythonStreamClient pythonStreamClient;

    public ProjectFileService(ProjectService projectService,
                              PythonAgentClient pythonAgentClient,
                              PythonStreamClient pythonStreamClient) {
        this.projectService = projectService;
        this.pythonAgentClient = pythonAgentClient;
        this.pythonStreamClient = pythonStreamClient;
    }

    public ProjectFileTreeResponse tree(String projectId, String path, int pageSize,
                                        String cursor, String ownerId) {
        projectService.requireOwnedProject(projectId, ownerId);
        if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
            throw new BaseException(ErrorCode.INVALID_ARGUMENT,
                    "page_size 必须在 1 到 " + MAX_PAGE_SIZE + " 之间");
        }
        String normalizedPath = normalizeRelativePath(path, true);
        String normalizedCursor = normalizeCursor(cursor);
        return pythonAgentClient.getFileTree(projectId, normalizedPath, pageSize, normalizedCursor);
    }

    public ProjectFileContentResponse content(String projectId, String path, String ownerId) {
        projectService.requireOwnedProject(projectId, ownerId);
        String normalizedPath = normalizeRelativePath(path, false);
        return pythonAgentClient.getFileContent(projectId, normalizedPath);
    }

    /** 下载单个文件；成功时直接写字节，不套 Result。 */
    public void download(String projectId, String path, String ownerId, HttpServletResponse response) {
        projectService.requireOwnedProject(projectId, ownerId);
        String normalizedPath = normalizeRelativePath(path, false);
        String fileName = fileNameOf(normalizedPath);

        try (PythonStreamClient.UpstreamStream upstream =
                     pythonStreamClient.openDownload(projectId, normalizedPath)) {
            prepareStreamResponse(response, "application/octet-stream", fileName,
                    upstream.contentLength());
            copy(upstream.body(), response.getOutputStream());
        } catch (IOException exception) {
            // 开始写响应后无法再改成普通 Result；关闭连接由容器和 try-with-resources 完成。
            log.warn("[文件下载中断] 项目ID: {}, 原因: {}", projectId, exception.getClass().getSimpleName());
        }
    }

    /** 下载项目 ZIP；ZIP 内容和大小由 Python 在开始响应前完成检查。 */
    public void archive(String projectId, String ownerId, HttpServletResponse response) {
        Project project = projectService.requireOwnedProject(projectId, ownerId);
        String fileName = safeArchiveName(project.getName());

        try (PythonStreamClient.UpstreamStream upstream = pythonStreamClient.openArchive(projectId)) {
            prepareStreamResponse(response, "application/zip", fileName, upstream.contentLength());
            copy(upstream.body(), response.getOutputStream());
        } catch (IOException exception) {
            log.warn("[项目压缩下载中断] 项目ID: {}, 原因: {}", projectId, exception.getClass().getSimpleName());
        }
    }

    private void prepareStreamResponse(HttpServletResponse response, String contentType,
                                       String fileName, long contentLength) {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType(contentType);
        response.setHeader(HttpHeaders.CONTENT_DISPOSITION, contentDisposition(fileName));
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader("X-Content-Type-Options", "nosniff");
        if (contentLength >= 0) {
            response.setContentLengthLong(contentLength);
        }
    }

    private void copy(InputStream input, OutputStream output) throws IOException {
        byte[] buffer = new byte[COPY_BUFFER_BYTES];
        int read;
        while ((read = input.read(buffer)) != -1) {
            output.write(buffer, 0, read);
        }
        output.flush();
    }

    /**
     * 只接受项目内相对路径。真实文件系统边界仍由 Python 检查，
     * 这里提前拒绝绝对路径、反斜杠、控制字符和 .. 片段。
     */
    static String normalizeRelativePath(String rawPath, boolean allowRoot) {
        String path = rawPath == null ? "" : rawPath;
        if (path.isEmpty()) {
            if (allowRoot) {
                return "";
            }
            throw new BaseException(ErrorCode.PROJECT_FILE_PATH_INVALID);
        }
        if (path.length() > MAX_PATH_LENGTH || path.startsWith("/")
                || path.indexOf('\\') >= 0 || path.matches("^[A-Za-z]:.*")) {
            throw new BaseException(ErrorCode.PROJECT_FILE_PATH_INVALID);
        }
        for (int index = 0; index < path.length(); index++) {
            char value = path.charAt(index);
            if (value < 0x20 || value == 0x7f) {
                throw new BaseException(ErrorCode.PROJECT_FILE_PATH_INVALID);
            }
        }
        String[] segments = path.split("/", -1);
        for (String segment : segments) {
            if (segment.isEmpty() || ".".equals(segment) || "..".equals(segment)) {
                throw new BaseException(ErrorCode.PROJECT_FILE_PATH_INVALID);
            }
        }
        return path;
    }

    private String normalizeCursor(String cursor) {
        if (cursor == null || cursor.isBlank()) {
            return null;
        }
        if (cursor.length() > MAX_CURSOR_LENGTH) {
            throw new BaseException(ErrorCode.INVALID_ARGUMENT, "cursor 长度不合法");
        }
        return cursor;
    }

    static String fileNameOf(String path) {
        int slash = path.lastIndexOf('/');
        String name = slash >= 0 ? path.substring(slash + 1) : path;
        return sanitizeFileName(name, "download");
    }

    static String safeArchiveName(String projectName) {
        String base = sanitizeFileName(projectName, "project");
        return base.toLowerCase().endsWith(".zip") ? base : base + ".zip";
    }

    private static String sanitizeFileName(String value, String fallback) {
        if (value == null) {
            return fallback;
        }
        StringBuilder cleaned = new StringBuilder();
        value.codePoints().forEach(codePoint -> {
            if (codePoint >= 0x20 && codePoint != 0x7f
                    && codePoint != '\\' && codePoint != '/' && codePoint != ':'
                    && codePoint != '*' && codePoint != '?' && codePoint != '"'
                    && codePoint != '<' && codePoint != '>' && codePoint != '|') {
                cleaned.appendCodePoint(codePoint);
            }
        });
        String result = cleaned.toString().trim();
        if (result.isEmpty() || ".".equals(result) || "..".equals(result)) {
            return fallback;
        }
        if (result.codePointCount(0, result.length()) <= 120) {
            return result;
        }
        return result.substring(0, result.offsetByCodePoints(0, 120));
    }

    static String contentDisposition(String fileName) {
        String safeName = sanitizeFileName(fileName, "download");
        String fallback = safeName.codePoints()
                .map(codePoint -> codePoint >= 0x20 && codePoint < 0x7f ? codePoint : '_')
                .collect(StringBuilder::new, StringBuilder::appendCodePoint, StringBuilder::append)
                .toString();
        if (fallback.isBlank()) {
            fallback = "download";
        }
        String encoded = URLEncoder.encode(safeName, StandardCharsets.UTF_8)
                .replace("+", "%20")
                .replace("*", "%2A");
        return "attachment; filename=\"" + fallback + "\"; filename*=UTF-8''" + encoded;
    }
}
