package com.Agent.javabackend.dto.ProjectDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.time.OffsetDateTime;

@Data
public class ProjectResponse {
    @JsonProperty("project_id")
    private String projectId;
    private String name;
    private String description;
    @JsonProperty("created_at")
    private OffsetDateTime createdAt;
    @JsonProperty("updated_at")
    private OffsetDateTime updatedAt;

}
