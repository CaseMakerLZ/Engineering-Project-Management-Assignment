package com.Agent.javabackend.exception;

import org.springframework.http.HttpStatus;

// 业务错误码。每个错误同时声明业务码、默认消息和对应的 HTTP 状态。
public enum ErrorCode {
    //成功
    SUCCESS(0,"成功", HttpStatus.OK),

    //通用请求错误域（10000-19999）
    INVALID_ARGUMENT(10001,"请求参数不合法",HttpStatus.BAD_REQUEST),

    //用户与权限域(20000–29999)
    //TODO: 要等用户业务开始写的时候再同步推进,这里先给出几个基本都会用到的
    USER_NOT_FOUND(20001,"未找到此用户",HttpStatus.NOT_FOUND),
    PASSWORD_ERROR(20002,"密码错误",HttpStatus.UNAUTHORIZED),

    //Agent任务域（30000-39999）
    AGENT_RUN_NOT_FOUND(30001,"Agent Run 不存在",HttpStatus.NOT_FOUND),
    AGENT_RUN_STATE_CONFLICT(30002,"Agent Run 当前状态不允许执行此操作",HttpStatus.CONFLICT),

    //Python Agent Service 通信域(40000-49999)
    AGENT_SERVICE_UNAVAILABLE(40001,"Agent服务暂不可用",HttpStatus.SERVICE_UNAVAILABLE),
    AGENT_SERVICE_TIMEOUT(40002,"Agent 服务调用超时",HttpStatus.GATEWAY_TIMEOUT),
    AGENT_SERVICE_AUTH_FAILED(40003,"Agent 服务鉴权失败",HttpStatus.BAD_GATEWAY),
    AGENT_SERVICE_RESPONSE_ERROR(40004,"Agent 服务返回异常",HttpStatus.BAD_GATEWAY),

    //其他未知异常域
    INTERNAL_SERVER_ERROR(90001,"系统内部错误",HttpStatus.INTERNAL_SERVER_ERROR);

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
