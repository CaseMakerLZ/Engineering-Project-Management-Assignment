package com.Agent.javabackend.Service;

import com.Agent.javabackend.dto.ConversationDTO.ContextMessage;
import com.Agent.javabackend.entity.MessageContainer.AgentTask;

import java.util.List;

/** 此Service用与上下文的管理，V1.0版本，后续应该要迭代*/
public interface ContextService {
    public List<ContextMessage> assembleContext(List<AgentTask> previous);
}
