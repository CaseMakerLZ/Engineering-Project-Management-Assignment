package com.Agent.javabackend.dto.ConversationDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
public class ConversationResponse {
    @JsonProperty("conversation_id")
    private String conversationId;
    @JsonProperty("project_id")
    private String projectId;
    private String title;
    private String status;
    @JsonProperty("created_at")
    private OffsetDateTime createdAt;
    @JsonProperty("updated_at")
    private OffsetDateTime updatedAt;

}
