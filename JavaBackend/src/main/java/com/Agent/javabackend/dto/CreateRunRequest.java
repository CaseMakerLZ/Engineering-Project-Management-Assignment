package com.Agent.javabackend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import com.Agent.javabackend.dto.ConversationDTO.ContextMessage;
import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateRunRequest {
    @JsonProperty("project_id")
    @Size(max=128,message="project_id长度不得超过128")
    private String projectId;

    @JsonProperty("conversation_id")
    private String conversationId;

    @NotBlank(message="prompt不得为空")
    @Size(max=20000,message="提示词长度不得超过20000")
    private String prompt;

    private List<ContextMessage> context;

    public CreateRunRequest(String projectId, String prompt) {
        this.projectId = projectId;
        this.prompt = prompt;
    }
}
