package com.Agent.javabackend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import com.Agent.javabackend.dto.ConversationDTO.ContextMessage;
import java.util.List;

/** Java 调用 Python Agent 服务时提交的一次任务请求。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateRunRequest {
    /** 项目 ID，表示这次任务属于哪个项目。 */
    @JsonProperty("project_id")
    @Size(max=128,message="project_id长度不得超过128")
    private String projectId;

    /** 对话 ID，表示这次任务属于哪段对话。 */
    @JsonProperty("conversation_id")
    private String conversationId;

    /** 用户本次输入的问题或指令。 */
    @NotBlank(message="prompt不得为空")
    @Size(max=20000,message="提示词长度不得超过20000")
    private String prompt;

    /** 之前的对话内容，帮助 Agent 理解本次问题。 */
    private List<ContextMessage> context;

    public CreateRunRequest(String projectId, String prompt) {
        this.projectId = projectId;
        this.prompt = prompt;
    }
}
