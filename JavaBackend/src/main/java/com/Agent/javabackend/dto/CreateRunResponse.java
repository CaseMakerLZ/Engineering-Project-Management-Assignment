package com.Agent.javabackend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateRunResponse {
    @JsonProperty("run_id")
    private String runId;
    private RunStatus status;
}
