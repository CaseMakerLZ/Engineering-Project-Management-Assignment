package com.Agent.javabackend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/** Python Agent Service 创建或取消 Run 时返回的最小状态。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class RunStatusResponse {
    /** Python 服务中这次运行的 ID。 */
    @JsonProperty("run_id")
    private String runId;
    /** 创建或取消后的状态。 */
    private RunStatus status;
}
