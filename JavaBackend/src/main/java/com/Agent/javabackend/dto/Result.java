package com.Agent.javabackend.dto;

import lombok.Data;

@Data
public class Result<T> {
    private Integer code; //编码：1成功，0为失败
    private String msg; //错误信息
    private T data; //数据

    //如果操作不需要给前端页面返回数据那么data就可以不赋值
    public static Result<Void> success() {
        Result<Void> result = new Result<>();
        result.code = 1;
        result.msg = "success";
        return result;
    }

    //和上面的注释意思类似，但是需要返回数据
    public static <T> Result<T> success(T data) {
        Result<T> result = new Result<T>();
        result.data = data;
        result.code = 1;
        result.msg = "success";
        return result;
    }

    public static Result<Void> error(String msg) {
        Result<Void> result = new Result<>();
        result.msg = msg;
        result.code = 0;
        return result;
    }
}
