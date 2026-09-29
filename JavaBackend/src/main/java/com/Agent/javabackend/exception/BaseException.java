package com.Agent.javabackend.exception;

import lombok.Getter;

/**
 * 业务异常基类，所有自定义业务异常继承此类
 */
@Getter
public class BaseException extends RuntimeException{
    //持有
    private final ErrorCode errorCode;
    //第一个构造函数的使用场景：业务判断手动抛
    public BaseException(ErrorCode errorCode) {
        super(errorCode.getMessage());
        this.errorCode = errorCode;
    }

    // 业务需要提供更具体的展示提示时，仍然保留统一的 ErrorCode。
    public BaseException(ErrorCode errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }

    //第二个构造函数的使用场景：捕获底层异常，包装成业务异常再往外抛，保留原始异常信息。
    public BaseException(ErrorCode errorCode, Throwable cause) {
        super(errorCode.getMessage(), cause);
        this.errorCode = errorCode;
    }

    public BaseException(ErrorCode errorCode, String message, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }

}
