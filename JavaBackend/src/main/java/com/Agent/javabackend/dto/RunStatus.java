package com.Agent.javabackend.dto;


import com.fasterxml.jackson.annotation.JsonCreator;

public enum RunStatus {
    CREATED("CREATED"),
    RUNNING("RUNNING"),
    COMPLETED("COMPLETED"),
    FAILED("FAILED"),
    CANCELLED("CANCELLED");

    private final String status;
    RunStatus(String status){
        this.status = status;
    }

    public String getStatus(){
        return this.status;
    }

    @JsonCreator
    public static RunStatus fromValue(String value) {
        for (RunStatus status : RunStatus.values()) {
            if (status.status.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("未知 RunStatus: " + value);
    }

}
