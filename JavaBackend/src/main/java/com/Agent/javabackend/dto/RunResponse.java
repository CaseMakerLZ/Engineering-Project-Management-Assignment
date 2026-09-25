package com.Agent.javabackend.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.hibernate.validator.constraints.kor.KorRRN;

import java.time.OffsetDateTime;

@AllArgsConstructor
@Data
@NoArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class RunResponse {
    @JsonProperty("run_id")
    private String runId;
    @JsonProperty("project_id")
    private String projectId;
    private RunStatus status;
    private String result;
    private String error;
    @JsonProperty("created_at")
    private OffsetDateTime createdAt;

    @JsonProperty("started_at")
    private OffsetDateTime startedAt;

    @JsonProperty("finished_at")
    private OffsetDateTime finishedAt;
}
