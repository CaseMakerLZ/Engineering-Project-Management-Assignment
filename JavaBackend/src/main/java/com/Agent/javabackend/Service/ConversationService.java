package com.Agent.javabackend.Service;

import com.Agent.javabackend.dto.ConversationDTO.*;
import com.Agent.javabackend.entity.MessageContainer.AgentTask;

public interface ConversationService {
    ConversationResponse create(String projectId, CreateConversationRequest request, String ownerId);
    ConversationResponse get(String conversationId, String ownerId);
    java.util.List<ConversationResponse> list(String projectId, String ownerId);
    CreateTurnResponse createTurn(String conversationId, CreateTurnRequest request, String ownerId);
    TurnResponse getTurn(String conversationId, String taskId, String ownerId);
    java.util.List<TurnResponse> listTurns(String conversationId, String ownerId);

    /** 校验 task 属于 URL 中的 conversation，并沿 conversation -> project 检查当前用户归属。 */
    AgentTask requireOwnedTask(String conversationId, String taskId, String ownerId);
}
