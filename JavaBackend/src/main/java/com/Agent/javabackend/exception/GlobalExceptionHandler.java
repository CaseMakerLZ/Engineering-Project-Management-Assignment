package com.Agent.javabackend.exception;

import com.Agent.javabackend.dto.Result;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {
    /**
     * 处理自定义的AgentService等方面的异常，后续的用户方面的业务、数据库方面的业务应该也可用
     */
    @ExceptionHandler(BaseException.class)
    public ResponseEntity<Result<Void>> handleBaseException(BaseException ex, HttpServletRequest request){
        // 1. 打印业务异常日志 (WARN级别，包含请求路径)
        log.warn("[业务异常] 请求路径: {}, 错误码: {}, 异常信息: {}", request.getRequestURI(), ex.getErrorCode().getCode(), ex.getMessage());
        // 2. 返回给前端明确的错误信息
        return ResponseEntity
                .status(ex.getErrorCode().getHttpStatus())
                .body(Result.error(ex.getErrorCode().getCode(), ex.getMessage()));
    }


    // @Valid 校验失败时，统一返回 HTTP 400 和业务码 10001。
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Result<Void>> handleValidationException(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {
        String message = ex.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .map(error -> error.getDefaultMessage())
                .orElse(ErrorCode.INVALID_ARGUMENT.getMessage());
        log.warn("[参数校验异常] 请求路径: {}, 异常信息: {}", request.getRequestURI(), message);
        return ResponseEntity
                .status(ErrorCode.INVALID_ARGUMENT.getHttpStatus())
                .body(Result.error(ErrorCode.INVALID_ARGUMENT.getCode(), message));
    }

    // 方法参数校验失败时，例如 @PathVariable 或 @RequestParam 上的约束失败。
    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<Result<Void>> handleMethodValidationException(
            HandlerMethodValidationException ex,
            HttpServletRequest request) {
        log.warn("[方法参数校验异常] 请求路径: {}, 异常信息: {}", request.getRequestURI(), ex.getMessage());
        return ResponseEntity
                .status(ErrorCode.INVALID_ARGUMENT.getHttpStatus())
                .body(Result.error(ErrorCode.INVALID_ARGUMENT.getCode(), ErrorCode.INVALID_ARGUMENT.getMessage()));
    }

    // 请求体不是合法 JSON，或 JSON 字段无法转换为 DTO 时，统一返回 400。
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Result<Void>> handleUnreadableMessage(
            HttpMessageNotReadableException ex,
            HttpServletRequest request) {
        log.warn("[请求体解析异常] 请求路径: {}, 异常信息: {}", request.getRequestURI(), ex.getMessage());
        return ResponseEntity
                .status(ErrorCode.INVALID_ARGUMENT.getHttpStatus())
                .body(Result.error(ErrorCode.INVALID_ARGUMENT.getCode(), ErrorCode.INVALID_ARGUMENT.getMessage()));
    }



    //兜底异常处理
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Result<Void>> handleException(Exception ex, HttpServletRequest request) {
        // 1. 打印详细的错误堆栈到日志 (ERROR级别，包含请求路径)
        log.error("[系统异常] 请求路径: {}", request.getRequestURI(), ex);
        // 2. 返回给前端一个通用的错误信息 (避免泄露敏感信息)
        ErrorCode errorCode = ErrorCode.INTERNAL_SERVER_ERROR;
        return ResponseEntity
                .status(errorCode.getHttpStatus())
                .body(Result.error(errorCode.getCode(), errorCode.getMessage()));
    }

}
