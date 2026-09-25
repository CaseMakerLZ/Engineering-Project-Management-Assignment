package com.Agent.javabackend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/** Python Agent Service 的任务消息查询响应。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class RunMessagesResponse {
    @JsonProperty("run_id")
    private String runId;

    private List<MessageResponse> messages;
}
