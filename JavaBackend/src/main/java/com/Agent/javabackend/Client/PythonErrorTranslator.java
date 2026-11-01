package com.Agent.javabackend.Client;

import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 把 Python 内部接口的错误翻译成 Java 业务错误。
 *
 * 只读取 detail.code，不把 detail.message 或原始响应正文送到浏览器，
 * 避免服务器路径、令牌或内部异常进入页面。
 */
final class PythonErrorTranslator {
    enum Kind {
        RUN,
        FILE,
        ARCHIVE,
        STREAM
    }

    private PythonErrorTranslator() {
    }

    static BaseException translate(int status, String responseBody, ObjectMapper mapper, Kind kind) {
        String code = extractCode(responseBody, mapper);

        ErrorCode byCode = mapCode(code, kind);
        if (byCode != null) {
            return new BaseException(byCode);
        }

        if (status == 401 || status == 403) {
            return new BaseException(ErrorCode.AGENT_SERVICE_AUTH_FAILED);
        }
        if (status == 408 || status == 504) {
            return new BaseException(ErrorCode.AGENT_SERVICE_TIMEOUT);
        }
        if (status == 503) {
            return new BaseException(ErrorCode.AGENT_SERVICE_UNAVAILABLE);
        }

        if (kind == Kind.RUN) {
            return switch (status) {
                case 404 -> new BaseException(ErrorCode.AGENT_RUN_NOT_FOUND);
                case 409 -> new BaseException(ErrorCode.AGENT_RUN_STATE_CONFLICT);
                case 422 -> new BaseException(ErrorCode.INVALID_ARGUMENT);
                default -> new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR);
            };
        }

        if (kind == Kind.STREAM) {
            return switch (status) {
                case 404 -> new BaseException(ErrorCode.AGENT_RUN_NOT_FOUND);
                case 429 -> new BaseException(ErrorCode.AGENT_STREAM_LIMIT);
                default -> new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR);
            };
        }

        return switch (status) {
            case 400 -> new BaseException(ErrorCode.INVALID_ARGUMENT);
            case 404 -> new BaseException(ErrorCode.PROJECT_FILE_NOT_FOUND);
            case 409 -> new BaseException(ErrorCode.PROJECT_FILE_CONFLICT);
            case 413 -> new BaseException(kind == Kind.ARCHIVE
                    ? ErrorCode.PROJECT_ARCHIVE_TOO_LARGE
                    : ErrorCode.PROJECT_FILE_TOO_LARGE);
            case 415 -> new BaseException(ErrorCode.PROJECT_FILE_UNSUPPORTED);
            case 422 -> new BaseException(ErrorCode.INVALID_ARGUMENT);
            case 429 -> new BaseException(ErrorCode.PROJECT_FILE_RATE_LIMITED);
            default -> new BaseException(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR);
        };
    }

    private static ErrorCode mapCode(String code, Kind kind) {
        if (code == null || code.isBlank()) {
            return null;
        }
        return switch (code) {
            case "PROJECT_BUSY" -> ErrorCode.PROJECT_BUSY;
            case "PROJECT_NOT_FOUND" -> ErrorCode.PROJECT_NOT_FOUND;
            case "SUBSCRIPTION_LIMIT" -> ErrorCode.AGENT_STREAM_LIMIT;
            case "PATH_INVALID", "INVALID_PATH", "INVALID_RELATIVE_PATH" ->
                    ErrorCode.PROJECT_FILE_PATH_INVALID;
            case "FILE_NOT_FOUND", "PROJECT_FILE_NOT_FOUND" -> ErrorCode.PROJECT_FILE_NOT_FOUND;
            case "FILE_TOO_LARGE", "CONTENT_TOO_LARGE", "PREVIEW_TOO_LARGE" ->
                    kind == Kind.ARCHIVE ? ErrorCode.PROJECT_ARCHIVE_TOO_LARGE : ErrorCode.PROJECT_FILE_TOO_LARGE;
            case "ARCHIVE_TOO_LARGE" -> ErrorCode.PROJECT_ARCHIVE_TOO_LARGE;
            case "UNSUPPORTED_ENCODING", "NOT_TEXT", "BINARY_FILE", "PREVIEW_UNSUPPORTED" ->
                    ErrorCode.PROJECT_FILE_UNSUPPORTED;
            case "CURSOR_INVALID", "CURSOR_EXPIRED", "DIRECTORY_CHANGED" ->
                    ErrorCode.PROJECT_FILE_CONFLICT;
            case "RATE_LIMITED", "TOO_MANY_REQUESTS" -> ErrorCode.PROJECT_FILE_RATE_LIMITED;
            default -> null;
        };
    }

    private static String extractCode(String responseBody, ObjectMapper mapper) {
        if (responseBody == null || responseBody.isBlank()) {
            return null;
        }
        try {
            JsonNode root = mapper.readTree(responseBody);
            JsonNode detail = root.get("detail");
            if (detail != null && detail.isObject()) {
                JsonNode code = detail.get("code");
                return code != null && code.isTextual() ? code.asText() : null;
            }
        } catch (RuntimeException ignored) {
            // 上游错误正文不是受控 JSON 时按 HTTP 状态翻译。
        }
        return null;
    }
}
