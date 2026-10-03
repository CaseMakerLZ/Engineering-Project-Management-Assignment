package com.Agent.javabackend.dto;

import lombok.Data;

/** Java 对外接口统一使用的返回格式。 */
@Data
public class Result<T> {
    /** 业务结果码，0 表示成功，其他值表示具体错误。 */
    private Integer code;
    /** 对结果的文字说明。 */
    private String msg;
    /** 成功时返回的数据，失败时通常为空。 */
    private T data;

    /** 返回一个没有数据的成功结果。 */
    public static Result<Void> success() {
        Result<Void> result = new Result<>();
        result.code = 0;
        result.msg = "success";
        return result;
    }

    /** 返回一个带数据的成功结果。 */
    public static <T> Result<T> success(T data) {
        Result<T> result = new Result<T>();
        result.data = data;
        result.code = 0;
        result.msg = "success";
        return result;
    }

    public static <T> Result<T> error(int code, String msg) {
        Result<T> result = new Result<>();
        result.msg = msg;
        result.code = code;
        return result;
    }
}
