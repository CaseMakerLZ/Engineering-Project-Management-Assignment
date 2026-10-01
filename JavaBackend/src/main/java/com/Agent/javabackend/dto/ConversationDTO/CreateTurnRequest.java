package com.Agent.javabackend.dto.ConversationDTO;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class CreateTurnRequest {
    @NotBlank(message = "prompt不得为空")
    @Size(max = 20000, message = "提示词长度不得超过20000")
    private String prompt;
}
