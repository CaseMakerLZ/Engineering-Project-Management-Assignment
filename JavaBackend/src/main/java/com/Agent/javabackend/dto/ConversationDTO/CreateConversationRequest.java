package com.Agent.javabackend.dto.ConversationDTO;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateConversationRequest {
    @NotBlank(message = "对话标题不得为空")
    @Size(max = 128, message = "对话标题长度不得超过128")
    private String title;
}
