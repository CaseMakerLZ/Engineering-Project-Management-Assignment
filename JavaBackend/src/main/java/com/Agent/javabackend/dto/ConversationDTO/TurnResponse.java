package com.Agent.javabackend.dto.ConversationDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import com.Agent.javabackend.dto.RunStatus;

import java.time.OffsetDateTime;

/** 返回给前端的一轮对话任务及其执行结果。 */
@Data
public class TurnResponse {
    /** Java 为这一轮生成的任务 ID。 */
    @JsonProperty("task_id")
    private String taskId;
    /** 这轮任务所属的对话 ID。 */
    @JsonProperty("conversation_id")
    private String conversationId;
    /** Python 服务中对应的运行 ID。 */
    @JsonProperty("python_run_id")
    private String pythonRunId;
    /** 用户这一轮提出的问题。 */
    private String prompt;
    /** 当前任务状态。 */
    private RunStatus status;
    /** Agent 完成后的回答。 */
    private String result;
    /** 任务失败时的错误说明。 */
    private String error;
    /** Java 创建这轮任务的时间。 */
    @JsonProperty("created_at")
    private OffsetDateTime createdAt;
    /** Python 开始执行这轮任务的时间。 */
    @JsonProperty("started_at")
    private OffsetDateTime startedAt;
    /** 任务结束的时间。 */
    @JsonProperty("finished_at")
    private OffsetDateTime finishedAt;
}
