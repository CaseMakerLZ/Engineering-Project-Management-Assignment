package com.Agent.javabackend.dto.ConversationDTO;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 创建一段新对话时，前端提交的数据。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateConversationRequest {
    /** 新对话的标题。 */
    @NotBlank(message = "对话标题不得为空")
    @Size(max = 128, message = "对话标题长度不得超过128")
    private String title;
}
