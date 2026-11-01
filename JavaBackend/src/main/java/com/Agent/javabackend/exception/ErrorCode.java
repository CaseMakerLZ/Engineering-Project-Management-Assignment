package com.Agent.javabackend.exception;

import org.springframework.http.HttpStatus;

// 业务错误码。每个错误同时声明业务码、默认消息和对应的 HTTP 状态。
public enum ErrorCode {
    //成功
    SUCCESS(0,"成功", HttpStatus.OK),

    //通用请求错误域（10000-19999）
    INVALID_ARGUMENT(10001,"请求参数不合法",HttpStatus.BAD_REQUEST),
    AUTH_TOKEN_INVALID(10002,"未登录或令牌已失效",HttpStatus.UNAUTHORIZED),

    //用户与权限域(20000–29999)
    USERNAME_ALREADY_EXISTS(20001,"用户名已存在",HttpStatus.CONFLICT),
    BAD_CREDENTIALS(20002,"用户名或密码错误",HttpStatus.UNAUTHORIZED),

    //Agent任务域（30000-39999）
    AGENT_RUN_NOT_FOUND(30001,"Agent Run 不存在",HttpStatus.NOT_FOUND),
    AGENT_RUN_STATE_CONFLICT(30002,"Agent Run 当前状态不允许执行此操作",HttpStatus.CONFLICT),
    PROJECT_NOT_FOUND(30003,"项目不存在",HttpStatus.NOT_FOUND),
    CONVERSATION_NOT_FOUND(30004,"对话不存在",HttpStatus.NOT_FOUND),
    CONVERSATION_STATE_CONFLICT(30005,"对话当前有正在执行的任务",HttpStatus.CONFLICT),
    AGENT_TASK_NOT_FOUND(30006,"对话任务不存在",HttpStatus.NOT_FOUND),
    PROJECT_WORKSPACE_PREPARATION_FAILED(30007,"项目目录准备失败",HttpStatus.SERVICE_UNAVAILABLE),
    PROJECT_FILE_NOT_FOUND(30008,"项目文件不存在",HttpStatus.NOT_FOUND),
    PROJECT_FILE_PATH_INVALID(30009,"项目文件路径不合法",HttpStatus.BAD_REQUEST),
    PROJECT_FILE_TOO_LARGE(30010,"项目文件超过大小限制",HttpStatus.PAYLOAD_TOO_LARGE),
    PROJECT_FILE_UNSUPPORTED(30011,"该文件不支持在线预览",HttpStatus.UNSUPPORTED_MEDIA_TYPE),
    PROJECT_BUSY(30012,"项目正在执行任务",HttpStatus.CONFLICT),
    PROJECT_FILE_CONFLICT(30013,"项目目录已变化，请刷新后重试",HttpStatus.CONFLICT),
    PROJECT_ARCHIVE_TOO_LARGE(30014,"项目压缩包超过大小限制",HttpStatus.PAYLOAD_TOO_LARGE),
    PROJECT_FILE_RATE_LIMITED(30015,"文件请求过于频繁，请稍后再试",HttpStatus.TOO_MANY_REQUESTS),
    LOCAL_DIRECTORY_NOT_FOUND(30016,"本地目录不存在",HttpStatus.NOT_FOUND),
    LOCAL_DIRECTORY_PATH_INVALID(30017,"本地目录路径不合法",HttpStatus.BAD_REQUEST),
    LOCAL_DIRECTORY_ALREADY_EXISTS(30018,"同名目录已存在",HttpStatus.CONFLICT),
    LOCAL_DIRECTORY_ACCESS_DENIED(30019,"没有权限访问该本地目录",HttpStatus.FORBIDDEN),
    LOCAL_DIRECTORY_UNAVAILABLE(30020,"本地目录服务暂不可用",HttpStatus.SERVICE_UNAVAILABLE),
    LOCAL_ACCESS_DENIED(30021,"本机请求校验失败",HttpStatus.FORBIDDEN),
    AGENT_TASK_PERSIST_FAILED(30022,"任务已创建但保存失败，请勿重复提交",HttpStatus.INTERNAL_SERVER_ERROR),
    LOCAL_PROJECT_SAVE_FAILED(30023,"项目保存失败，已创建的目录保留",HttpStatus.INTERNAL_SERVER_ERROR),

    //Python Agent Service 通信域(40000-49999)
    AGENT_SERVICE_UNAVAILABLE(40001,"Agent服务暂不可用",HttpStatus.SERVICE_UNAVAILABLE),
    AGENT_SERVICE_TIMEOUT(40002,"Agent 服务调用超时",HttpStatus.GATEWAY_TIMEOUT),
    AGENT_SERVICE_AUTH_FAILED(40003,"Agent 服务鉴权失败",HttpStatus.BAD_GATEWAY),
    AGENT_SERVICE_RESPONSE_ERROR(40004,"Agent 服务返回异常",HttpStatus.BAD_GATEWAY),
    AGENT_STREAM_LIMIT(40005,"实时连接数已达上限",HttpStatus.TOO_MANY_REQUESTS),
    AGENT_STREAM_CONNECTION_LIMIT(40006,"Java 实时连接数已达上限",HttpStatus.TOO_MANY_REQUESTS),

    //其他未知异常域
    INTERNAL_SERVER_ERROR(50000,"系统内部错误",HttpStatus.INTERNAL_SERVER_ERROR);

    private final int code;
    private final String message;
    private final HttpStatus httpStatus;

    ErrorCode(int code,String message,HttpStatus httpStatus){
        this.code = code;
        this.message = message;
        this.httpStatus = httpStatus;
    }

    public HttpStatus getHttpStatus() {
        return httpStatus;
    }

    public String getMessage() {
        return message;
    }

    public int getCode() {
        return code;
    }
}
