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
    /** Python 服务为这次运行生成的 ID。 */
    @JsonProperty("run_id")
    private String runId;
    /** 这次运行所属的项目 ID。 */
    @JsonProperty("project_id")
    private String projectId;
    /** 当前任务状态。 */
    private RunStatus status;
    /** Agent 完成后的最终回答。 */
    private String result;
    /** Agent 执行失败时的错误说明。 */
    private String error;
    /** 任务创建时间。 */
    @JsonProperty("created_at")
    private OffsetDateTime createdAt;

    /** 任务开始执行时间。 */
    @JsonProperty("started_at")
    private OffsetDateTime startedAt;

    /** 任务完成、失败或取消的时间。 */
    @JsonProperty("finished_at")
    private OffsetDateTime finishedAt;
}
