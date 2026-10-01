package com.Agent.javabackend.dto.ConversationDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
public class TurnResponse {
    @JsonProperty("task_id")
    private String taskId;
    @JsonProperty("conversation_id")
    private String conversationId;
    @JsonProperty("python_run_id")
    private String pythonRunId;
    private String prompt;
    private String status;
    private String result;
    private String error;
    @JsonProperty("created_at")
    private OffsetDateTime createdAt;
    @JsonProperty("started_at")
    private OffsetDateTime startedAt;
    @JsonProperty("finished_at")
    private OffsetDateTime finishedAt;
}
