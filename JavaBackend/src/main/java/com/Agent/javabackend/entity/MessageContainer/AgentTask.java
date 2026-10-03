package com.Agent.javabackend.entity.MessageContainer;

import lombok.Data;
import com.Agent.javabackend.dto.RunStatus;

import java.time.OffsetDateTime;

/** 数据库中的一轮 Agent 任务记录。 */
@Data
public class AgentTask {
    /** Java 为这一轮任务生成的 ID。 */
    private String id;
    /** 这轮任务所属的对话 ID。 */
    private String conversationId;
    /** 用户提交的问题。 */
    private String prompt;
    /** Python Agent 服务中的运行 ID。 */
    private String pythonRunId;
    /** 当前任务状态。 */
    private RunStatus status;
    /** Agent 完成后的回答。 */
    private String result;
    /** 任务失败时的错误说明。 */
    private String error;
    /** Java 创建任务的时间。 */
    private OffsetDateTime createdAt;
    /** Python 开始运行的时间。 */
    private OffsetDateTime startedAt;
    /** 任务完成、失败或取消的时间。 */
    private OffsetDateTime finishedAt;
}
