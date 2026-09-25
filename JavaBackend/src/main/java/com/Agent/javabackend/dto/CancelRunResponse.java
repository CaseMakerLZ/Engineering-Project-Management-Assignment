package com.Agent.javabackend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/** Python Agent Service 的取消任务响应。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class CancelRunResponse {
    @JsonProperty("run_id")
    private String runId;

    private RunStatus status;
}
