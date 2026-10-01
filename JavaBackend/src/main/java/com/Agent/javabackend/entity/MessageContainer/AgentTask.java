package com.Agent.javabackend.entity.MessageContainer;

import lombok.Data;

import java.time.OffsetDateTime;

@Data
public class AgentTask {
    /**
     * id
     * conversation_id
     * prompt
     * python_run_id
     * status
     * result
     * error
     * created_at
     * started_at
     * finished_at
     */
    private String id;
    private String conversationId;
    private String prompt;
    private String pythonRunId;
    private String status;
    private String result;
    private String error;
    private OffsetDateTime createdAt;
    private OffsetDateTime startedAt;
    private OffsetDateTime finishedAt;
}
