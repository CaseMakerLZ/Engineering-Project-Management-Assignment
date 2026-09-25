package com.Agent.javabackend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateRunRequest {
    @JsonProperty("project_id")
    @Size(max=128,message="project_id长度不得超过128")
    private String projectId;

    @NotBlank(message="prompt不得为空")
    @Size(max=20000,message="提示词长度不得超过20000")
    private String prompt;
}
