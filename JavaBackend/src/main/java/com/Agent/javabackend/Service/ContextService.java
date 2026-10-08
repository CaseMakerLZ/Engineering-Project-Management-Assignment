package com.Agent.javabackend.Service;

import com.Agent.javabackend.dto.ConversationDTO.ContextMessage;
import com.Agent.javabackend.entity.MessageContainer.AgentTask;

import java.util.List;

/**
 * 负责从历史任务中挑选本轮 Agent 需要看到的对话内容。
 *
 * 当前版本只处理最近的完整问答轮次；以后可以在这里加入摘要和长度预算。
 */
public interface ContextService {
    List<ContextMessage> assembleContext(List<AgentTask> previous);
}
