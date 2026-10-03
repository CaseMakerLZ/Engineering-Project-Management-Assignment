package com.Agent.javabackend.dto.ConversationDTO;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** 向已有对话提交新一轮问题时，前端提交的数据。 */
@Data
public class CreateTurnRequest {
    /** 用户这一轮要询问 Agent 的内容。 */
    @NotBlank(message = "prompt不得为空")
    @Size(max = 20000, message = "提示词长度不得超过20000")
    private String prompt;
}
