package com.Agent.javabackend.dto.ConversationDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateTurnResponse {
    @JsonProperty("task_id")
    private String taskId;
    @JsonProperty("conversation_id")
    private String conversationId;
    @JsonProperty("python_run_id")
    private String pythonRunId;
    private String status;
}
