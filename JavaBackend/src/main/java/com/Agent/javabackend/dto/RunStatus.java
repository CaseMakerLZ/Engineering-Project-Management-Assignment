package com.Agent.javabackend.dto;


import com.fasterxml.jackson.annotation.JsonCreator;

/** 一次 Agent 运行可能处于的状态。 */
public enum RunStatus {
    CREATED("CREATED"),
    RUNNING("RUNNING"),
    COMPLETED("COMPLETED"),
    FAILED("FAILED"),
    CANCELLED("CANCELLED");

    /** 对外传输时使用的状态文字。 */
    private final String status;
    RunStatus(String status){
        this.status = status;
    }

    public String getStatus(){
        return this.status;
    }

    @JsonCreator
    /** 把 Python 返回的状态文字转换成 Java 状态。 */
    public static RunStatus fromValue(String value) {
        for (RunStatus status : RunStatus.values()) {
            if (status.status.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("未知 RunStatus: " + value);
    }

}
