package com.Agent.javabackend.dto.ConversationDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import com.Agent.javabackend.dto.RunStatus;

/** 创建一轮任务后，Java 返回给前端的任务凭据。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateTurnResponse {
    /** Java 为这一轮生成的任务 ID。 */
    @JsonProperty("task_id")
    private String taskId;
    /** 这轮任务所属的对话 ID。 */
    @JsonProperty("conversation_id")
    private String conversationId;
    /** Python 服务中对应的运行 ID。 */
    @JsonProperty("python_run_id")
    private String pythonRunId;
    /** 当前任务状态。 */
    private RunStatus status;
}
